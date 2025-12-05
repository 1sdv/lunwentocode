"""
代码生成Agent - 根据任务生成Python代码
"""
import json
from typing import List, Optional, Dict, Any
from app.core.base_agent import BaseAgent
from app.core.llm import LLM
from app.schemas.models import (
    CodeTask, 
    GeneratedCode, 
    AnalysisResult,
    DataFileInfo
)
from app.config.settings import settings
from app.utils.logger import logger


# 代码生成工具定义
CODER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_code",
            "description": "生成Python代码来完成指定任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "完整的Python代码"
                    },
                    "file_name": {
                        "type": "string", 
                        "description": "代码文件名，如 data_preprocessing.py"
                    },
                    "description": {
                        "type": "string",
                        "description": "代码功能描述"
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "依赖的Python库列表"
                    }
                },
                "required": ["code", "file_name", "description"]
            }
        }
    }
]


class CoderAgent(BaseAgent):
    """代码生成Agent - 无状态设计，每个任务独立生成"""
    
    def __init__(self, llm: LLM):
        super().__init__(llm)
        
    @property
    def system_prompt(self) -> str:
        return """你是一个专业的Python代码生成专家，专门为毕业论文生成高质量的可运行代码。

## 代码规范
1. 代码必须完整、可直接运行
2. 包含必要的import语句
3. 添加清晰的中文注释
4. 使用规范的变量命名
5. 包含错误处理
6. 数据文件路径使用相对路径

## 代码风格
- 使用pandas处理数据
- 使用matplotlib/seaborn进行可视化
- 使用scikit-learn进行机器学习
- 代码结构清晰，函数化设计

## 输出要求
- 每个任务生成一个独立的.py文件
- 代码可以独立运行
- 包含main函数作为入口
- 打印关键结果

请使用generate_code工具生成代码。"""
    
    async def run(
        self, 
        analysis_result: AnalysisResult,
        data_files: Optional[List[DataFileInfo]] = None
    ) -> List[GeneratedCode]:
        """
        根据分析结果生成代码（每个任务独立调用LLM）
        
        Args:
            analysis_result: 内容分析结果
            data_files: 数据文件信息
            
        Returns:
            List[GeneratedCode]: 生成的代码列表
        """
        logger.info(f"开始生成代码，共 {len(analysis_result.code_tasks)} 个任务")
        
        generated_codes: List[GeneratedCode] = []
        
        # 构建项目上下文（所有任务共享）
        context = self._build_context(analysis_result, data_files)
        
        # 按优先级排序任务
        sorted_tasks = sorted(analysis_result.code_tasks, key=lambda x: x.priority)
        
        # 逐个独立生成代码（每个任务独立调用LLM，不依赖历史）
        for task in sorted_tasks:
            logger.info(f"生成任务: {task.title}")
            code = await self._generate_code_for_task(task, context, data_files)
            if code:
                generated_codes.append(code)
        
        # 生成主程序
        main_code = await self._generate_main_program(generated_codes, context)
        if main_code:
            generated_codes.append(main_code)
        
        logger.info(f"代码生成完成，共 {len(generated_codes)} 个文件")
        return generated_codes
    
    def _build_context(
        self, 
        analysis_result: AnalysisResult,
        data_files: Optional[List[DataFileInfo]]
    ) -> str:
        """构建上下文信息"""
        context = f"""## 项目背景
论文类型: {analysis_result.thesis_type.value}
研究方法: {analysis_result.research_method}
技术栈: {', '.join(analysis_result.tech_stack)}
依赖库: {', '.join(analysis_result.libraries)}

## 数据信息
"""
        if data_files:
            for df in data_files:
                context += f"\n### {df.file_name}\n"
                context += f"- 类型: {df.file_type}\n"
                if df.columns:
                    context += f"- 列名: {df.columns}\n"
                if df.row_count:
                    context += f"- 行数: {df.row_count}\n"
                if df.sample_data:
                    context += f"- 样本数据: {df.sample_data[:2]}\n"
        else:
            context += "无额外数据文件，需要根据论文描述模拟或生成示例数据。\n"
        
        context += f"\n## 代码任务列表\n"
        for task in analysis_result.code_tasks:
            context += f"\n### {task.title}\n"
            context += f"- 类型: {task.task_type.value}\n"
            context += f"- 描述: {task.description}\n"
            if task.requirements:
                context += f"- 要求: {task.requirements}\n"
        
        return context
    
    async def _generate_code_for_task(
        self, 
        task: CodeTask,
        context: str,
        data_files: Optional[List[DataFileInfo]]
    ) -> Optional[GeneratedCode]:
        """为单个任务独立生成代码（无历史依赖）"""
        
        prompt = f"""请为以下任务生成Python代码:

{context}

## 当前任务
- 任务ID: {task.task_id}
- 标题: {task.title}
- 类型: {task.task_type.value}
- 描述: {task.description}
- 要求: {task.requirements}
- 输入: {task.input_data}
- 期望输出: {task.expected_output}

请使用generate_code工具生成完整的Python代码文件。
代码必须:
1. 可以独立运行
2. 包含所有必要的import
3. 有清晰的注释
4. 包含main函数
5. 处理可能的异常"""

        try:
            # 独立调用LLM，不使用历史
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm.chat(
                messages=messages,
                tools=CODER_TOOLS,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            
            # 检查是否有工具调用
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_call = message.tool_calls[0]
                if tool_call.function.name == "generate_code":
                    args = json.loads(tool_call.function.arguments)
                    
                    # 处理dependencies可能是字符串的情况
                    deps = args.get("dependencies", [])
                    if isinstance(deps, str):
                        try:
                            deps = json.loads(deps)
                        except:
                            deps = []
                    
                    return GeneratedCode(
                        task_id=task.task_id,
                        file_name=args.get("file_name", f"{task.task_type.value}.py"),
                        code=args.get("code", ""),
                        description=args.get("description", task.description),
                        dependencies=deps if isinstance(deps, list) else []
                    )
            
            # 如果没有工具调用，尝试从文本中提取代码
            if message.content:
                code = self._extract_code_from_text(message.content, task)
                if code:
                    return code
                    
        except Exception as e:
            logger.error(f"生成代码失败: {e}")
        
        return None
    
    def _extract_code_from_text(self, text: str, task: CodeTask) -> Optional[GeneratedCode]:
        """从文本中提取代码"""
        # 查找代码块
        import re
        code_pattern = r'```python\n(.*?)```'
        matches = re.findall(code_pattern, text, re.DOTALL)
        
        if matches:
            code = matches[0]
            return GeneratedCode(
                task_id=task.task_id,
                file_name=f"{task.task_type.value}.py",
                code=code,
                description=task.description,
                dependencies=[]
            )
        return None
    
    async def _generate_main_program(
        self, 
        generated_codes: List[GeneratedCode],
        context: str
    ) -> Optional[GeneratedCode]:
        """生成主程序（独立调用）"""
        if not generated_codes:
            return None
        
        # 收集所有生成的文件及其描述
        file_info = "\n".join([
            f"- {c.file_name}: {c.description}" 
            for c in generated_codes
        ])
        
        prompt = f"""请生成一个主程序 main.py，用于协调运行以下代码文件:

{context}

## 已生成的代码文件
{file_info}

主程序应该:
1. 按正确顺序导入和调用各个模块
2. 提供命令行参数支持（可选运行特定模块）
3. 包含运行说明
4. 处理异常并给出友好提示

使用generate_code工具生成代码。"""

        try:
            # 独立调用LLM
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm.chat(
                messages=messages,
                tools=CODER_TOOLS,
                tool_choice="auto"
            )
            
            message = response.choices[0].message
            
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_call = message.tool_calls[0]
                if tool_call.function.name == "generate_code":
                    args = json.loads(tool_call.function.arguments)
                    
                    # 处理dependencies可能是字符串的情况
                    deps = args.get("dependencies", [])
                    if isinstance(deps, str):
                        try:
                            deps = json.loads(deps)
                        except:
                            deps = []
                    
                    return GeneratedCode(
                        task_id="main",
                        file_name="main.py",
                        code=args.get("code", ""),
                        description="主程序入口",
                        dependencies=deps if isinstance(deps, list) else []
                    )
            
            # 如果没有工具调用，尝试从文本提取
            if message.content:
                return self._extract_main_from_text(message.content)
                    
        except Exception as e:
            logger.error(f"生成主程序失败: {e}")
        
        return None
    
    def _extract_main_from_text(self, text: str) -> Optional[GeneratedCode]:
        """从文本中提取主程序代码"""
        import re
        code_pattern = r'```python\n(.*?)```'
        matches = re.findall(code_pattern, text, re.DOTALL)
        
        if matches:
            return GeneratedCode(
                task_id="main",
                file_name="main.py",
                code=matches[0],
                description="主程序入口",
                dependencies=[]
            )
        return None
