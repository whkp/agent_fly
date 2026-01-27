#!/usr/bin/env python3
"""
Agent 主程序 - 适配 px4ctrl 控制器

架构:
    tools.py (Agent工具) ──Topic──▶ px4ctrl ──▶ MAVROS ──▶ 实际机器人
"""
import os
import json
import threading
import queue
import time
import sys
from typing import Dict, Any, Optional

# --- ROS ---
import rospy
from std_msgs.msg import String

# --- LangChain & Pydantic ---
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field

# 添加当前模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import AgentTools
from llm_wrapper import LLMWrapper, ModelType


# 清除代理
for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_var, None)


# ==============================================================================
# 1. 定义输出格式 Schema
# ==============================================================================
class AgentActionSchema(BaseModel):
    thought: str = Field(description="思考过程：分析当前状态、任务进度，并决定下一步操作")
    action_name: str = Field(description="工具名称：必须是工具列表中提供的名称，任务结束时填 'Final'")
    action_params: Dict[str, Any] = Field(description="工具参数：键值对形式的字典，例如 {'x': 10, 'y': 5}")
    final_message: Optional[str] = Field(description="如果action_name是Final，填入给用户的最终回复", default=None)


# ==============================================================================
# 2. 安全管理层 (Safety Layer)
# ==============================================================================
class SafetyManager:
    """负责在指令下发给无人机前进行参数校验"""
    def __init__(self):
        self.MIN_Z = 1.0
        self.MAX_Z = 15.0
        self.SAFE_XY_RANGE = 50.0

    def validate(self, action_name: str, params: dict, current_state: dict) -> tuple:
        target_z = None
        if action_name == "takeoff":
            target_z = params.get("height")
        elif action_name == "set_goal":
            target_z = params.get("z")

        if target_z is not None:
            try:
                z_val = float(target_z)
                if z_val < self.MIN_Z:
                    return False, f"安全拦截: 目标高度 {z_val}m 低于最小安全高度 {self.MIN_Z}m"
                if z_val > self.MAX_Z:
                    return False, f"安全拦截: 目标高度 {z_val}m 高于最大安全高度 {self.MAX_Z}m"
            except ValueError:
                return False, "安全拦截: 高度参数非数字"

        if action_name == "set_goal":
            try:
                cur_x = current_state.get('x', 0)
                cur_y = current_state.get('y', 0)
                tar_x = float(params.get('x', cur_x))
                tar_y = float(params.get('y', cur_y))
                
                dist = ((tar_x - cur_x)**2 + (tar_y - cur_y)**2) ** 0.5
                if dist > 20.0:
                    return False, f"安全拦截: 单次指令移动距离 {dist:.1f}m 过大，请分步执行"
            except:
                pass

        return True, "Safe"


# ==============================================================================
# 3. Agent 主类
# ==============================================================================
class AgentRobot:
    def __init__(self):
        self._init_ros()
        
        # 初始化核心组件
        self.agent_tool = AgentTools()
        self.safety = SafetyManager()
        
        # 初始化 LLM（使用封装层）
        model_type = rospy.get_param('~llm_model', 'qwen3-max')
        temperature = rospy.get_param('~llm_temperature', 0.1)
        
        try:
            self.llm_wrapper = LLMWrapper(model_type=model_type, temperature=temperature)
            self.llm = self.llm_wrapper.get_llm()
        except ValueError as e:
            rospy.logfatal(str(e))
            raise
        
        # 解析器
        self.parser = PydanticOutputParser(pydantic_object=AgentActionSchema)
        
        # 记忆（增加窗口大小）
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        # 加载提示词
        self._load_prompts()

    def _init_ros(self):
        rospy.init_node('agent_node', anonymous=False)
        self.log_pub = rospy.Publisher('/agent_node/agent_log', String, queue_size=50)
        rospy.Subscriber('/agent_node/user_command', String, self.ui_command_callback)
        
        self.cmd_queue = queue.Queue()
        self.interrupt_flag = False
        self.looping = False
        
        threading.Thread(target=self.cli_input_thread, daemon=True).start()
    
    def _load_prompts(self):
        """从文件加载提示词"""
        cfg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cfg')
        
        # 加载主提示词
        prompt_file = os.path.join(cfg_dir, 'prompt_agent.txt')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()
        
        # 加载指导原则
        guidelines_file = os.path.join(cfg_dir, 'guidelines.txt')
        with open(guidelines_file, 'r', encoding='utf-8') as f:
            self.guidelines = f.read()
        
        # 加载示例
        examples_file = os.path.join(cfg_dir, 'examples.txt')
        with open(examples_file, 'r', encoding='utf-8') as f:
            self.examples = f.read()
        
        rospy.loginfo("✅ 提示词加载完成")

    def get_prompt_template(self, current_state_str, tools_desc):
        """构建提示词"""
        # 使用加载的模板
        template_str = self.prompt_template.format(
            current_state=current_state_str,
            tools_desc=tools_desc,
            guidelines=self.guidelines,
            examples=self.examples,
            format_instructions=self.parser.get_format_instructions()
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", template_str),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])
        
        return prompt

    def get_formatted_state(self):
        try:
            s = self.agent_tool.get_status_dict()
            return f"坐标(x,y,z): ({s['x']}, {s['y']}, {s['z']}) | Yaw: {s['yaw']}° | 状态: {s['status']}"
        except Exception as e:
            return "状态获取中..."

    def publish_log(self, role, type_str, content):
        msg = json.dumps({"role": role, "type": type_str, "content": content}, ensure_ascii=False)
        self.log_pub.publish(msg)

    def cli_input_thread(self):
        while not rospy.is_shutdown():
            try:
                user_input = input("\n")
                if user_input.strip():
                    self.cmd_queue.put(user_input)
                    if self.looping: self.interrupt_flag = True
            except EOFError:
                break

    def ui_command_callback(self, msg):
        self.cmd_queue.put(msg.data)
        if self.looping: self.interrupt_flag = True

    def run_one_task(self, user_question):
        self.looping = True
        print(f"\n🚀 开始任务: {user_question}")
        self.publish_log("user", "Question", user_question)
        
        self.memory.chat_memory.add_user_message(user_question)
        
        max_turns = 15
        turn = 0
        
        while turn < max_turns and not rospy.is_shutdown():
            if self.interrupt_flag:
                print("\033[33m⏸ 检测到用户输入，正在中断当前任务...\033[0m")
                self.interrupt_flag = False
                new_cmd = self.cmd_queue.get()
                self.memory.chat_memory.add_user_message(f"用户中断并输入新指令: {new_cmd}")
                print(f"👉 切换到新指令: {new_cmd}")
                continue

            state_str = self.get_formatted_state()
            tools_str = self.agent_tool.get_tools_description()
            
            prompt = self.get_prompt_template(state_str, tools_str)
            chain = prompt | self.llm | self.parser
            
            print(f"\n\033[34m--- Round {turn + 1} [State: {state_str}] ---\033[0m")

            try:
                history = self.memory.load_memory_variables({})['history']
                
                # 构建完整的 prompt（用于日志）
                prompt_text = prompt.format(
                    history=history,
                    input="请根据当前状态继续执行。" if turn > 0 else "开始规划并执行。"
                )
                
                # 调用 LLM
                response: AgentActionSchema = chain.invoke({
                    "history": history,
                    "input": "请根据当前状态继续执行。" if turn > 0 else "开始规划并执行。"
                })
                
                # 记录日志
                response_text = f"Thought: {response.thought}\nAction: {response.action_name}({response.action_params})"
                self.llm_wrapper.log_interaction(str(prompt_text), response_text)
                
            except Exception as e:
                print(f"⚠️ 解析失败或网络错误: {e}")
                self.memory.chat_memory.add_ai_message("SYSTEM: 上一轮输出格式错误，请严格遵守JSON格式。")
                time.sleep(1)
                continue

            thought = response.thought
            action = response.action_name
            params = response.action_params
            
            print(f"🧠 Thought: {thought}")
            self.publish_log("assistant", "Thought", thought)
            self.memory.chat_memory.add_ai_message(f"Thought: {thought}\nAction: {action}({params})")

            if action == "Final":
                final_msg = response.final_message or "任务完成"
                print(f"✅ Final Answer: {final_msg}\n")
                self.publish_log("assistant", "Final", final_msg)
                self.memory.chat_memory.add_ai_message(final_msg)
                break

            observation = ""
            tool_obj = next((t for t in self.agent_tool.tools if t['name'] == action), None)
            
            if tool_obj:
                current_state_dict = self.agent_tool.get_status_dict()
                is_safe, warning = self.safety.validate(action, params, current_state_dict)
                
                if is_safe:
                    print(f"🛠  Action: {action} {params}")
                    self.publish_log("assistant", "Action", f"{action} {params}")
                    try:
                        res = tool_obj['func'](params)
                        observation = str(res['result']) if isinstance(res, dict) and 'result' in res else str(res)
                    except Exception as err:
                        observation = f"Tool Error: {str(err)}"
                else:
                    print(f"🛡️  Safety Block: {warning}")
                    observation = f"Error: 动作被安全层拒绝。原因: {warning}"
            else:
                observation = f"Error: 找不到名为 '{action}' 的工具，请检查工具列表。"

            print(f"👀 Observation: {observation}")
            self.publish_log("assistant", "Observation", observation)
            self.memory.chat_memory.add_user_message(f"System Observation: {observation}")
            
            turn += 1
            time.sleep(0.5)

        self.looping = False
        if turn >= max_turns:
            print("⚠️ 达到最大对话轮次，任务强制结束。")

    def run_loop(self):
        print("🤖 Agent 就绪。请在终端输入指令 (输入 'q' 退出):")
        while not rospy.is_shutdown():
            try:
                user_input = self.cmd_queue.get()
                if user_input.lower() in ["q", "quit", "exit"]:
                    print("Bye!")
                    break
                self.run_one_task(user_input)
            except KeyboardInterrupt:
                break


if __name__ == "__main__":
    agent = AgentRobot()
    rospy.sleep(1)
    agent.run_loop()
