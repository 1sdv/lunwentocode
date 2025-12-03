"""
代码验证Agent - 验证生成的代码并自动修复错误
"""
import ast
import sys
import subprocess
import tempfile
import os
from typing import List, Optional, Tuple
from app.core.base_agent import BaseAgent
from app.core.llm import LLM
from app.schemas.models import GeneratedCode, ValidationResult
from app.config.settings import settings
from app.utils.logger import logger


class ValidatorAgent(BaseAgent):
    """代码验证Agent - 无状态设计"""
    
    def __init__(self, llm: LLM):
        super().__init__(llm)
        self.max_retries = settings.MAX_CODE_RETRIES
        
    @property
    def system_prompt(self) -> str:
        return """你是一个专业的Python代码审查和修复专家。
你的任务是:
1. 检查代码语法错误
2. 检查导入语句是否正确
3. 检查逻辑错误
4. 修复发现的问题
5. 优化代码质量

修复代码时请:
- 保持原有功能不变
- 添加必要的错误处理
- 确保代码可以独立运行
- 保留原有注释并添加必要的新注释"""
    
    async def run(self, generated_codes: List[GeneratedCode]) -> List[ValidationResult]:
        """
        验证所有生成的代码
        
        Args:
            generated_codes: 生成的代码列表
            
        Returns:
            List[ValidationResult]: 验证结果列表
        """
        logger.info(f"开始验证代码，共 {len(generated_codes)} 个文件")
        
        results = []
        for code in generated_codes:
            result = await self._validate_single_code(code)
            results.append(result)
        
        # 统计结果
        valid_count = sum(1 for r in results if r.is_valid)
        logger.info(f"验证完成: {valid_count}/{len(results)} 个文件通过")
        
        return results
    
    async def _validate_single_code(self, code: GeneratedCode) -> ValidationResult:
        """验证单个代码文件"""
        logger.info(f"验证: {code.file_name}")
        
        current_code = code.code
        retry_count = 0
        
        while retry_count < self.max_retries:
            # 1. 语法检查
            syntax_ok, syntax_error = self._check_syntax(current_code)
            
            if not syntax_ok:
                logger.warning(f"语法错误: {syntax_error}")
                # 尝试修复
                fixed_code = await self._fix_code(current_code, f"语法错误: {syntax_error}")
                if fixed_code:
                    current_code = fixed_code
                    retry_count += 1
                    continue
                else:
                    return ValidationResult(
                        task_id=code.task_id,
                        is_valid=False,
                        syntax_check=False,
                        error_message=syntax_error,
                        suggestions=["请检查代码语法"]
                    )
            
            # 2. 导入检查
            import_ok, import_error = self._check_imports(current_code)
            
            if not import_ok:
                logger.warning(f"导入错误: {import_error}")
                fixed_code = await self._fix_code(current_code, f"导入错误: {import_error}")
                if fixed_code:
                    current_code = fixed_code
                    retry_count += 1
                    continue
                else:
                    return ValidationResult(
                        task_id=code.task_id,
                        is_valid=False,
                        syntax_check=True,
                        import_check=False,
                        error_message=import_error,
                        suggestions=["请检查导入语句"]
                    )
            
            # 3. 静态分析
            analysis_ok, analysis_issues = self._static_analysis(current_code)
            
            suggestions = []
            if not analysis_ok:
                suggestions = analysis_issues
            
            # 验证通过
            return ValidationResult(
                task_id=code.task_id,
                is_valid=True,
                syntax_check=True,
                import_check=True,
                execution_check=False,  # 不实际执行
                suggestions=suggestions,
                fixed_code=current_code if current_code != code.code else None
            )
        
        # 超过最大重试次数
        return ValidationResult(
            task_id=code.task_id,
            is_valid=False,
            error_message=f"超过最大重试次数({self.max_retries})",
            suggestions=["代码存在问题，请手动检查"]
        )
    
    def _check_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """检查语法"""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"第{e.lineno}行: {e.msg}"
    
    def _check_imports(self, code: str) -> Tuple[bool, Optional[str]]:
        """检查导入语句"""
        try:
            tree = ast.parse(code)
            
            # 收集所有导入
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split('.')[0])
            
            # 检查标准库和常用库
            standard_libs = {
                'os', 'sys', 'json', 're', 'math', 'random', 'datetime',
                'collections', 'itertools', 'functools', 'typing',
                'pathlib', 'time', 'copy', 'warnings', 'logging'
            }
            
            common_libs = {
                'numpy', 'pandas', 'matplotlib', 'seaborn', 'sklearn',
                'scipy', 'statsmodels', 'torch', 'tensorflow', 'keras',
                'requests', 'bs4', 'lxml', 'openpyxl', 'xlrd'
            }
            
            # 简单检查：只验证语法正确性，不验证是否安装
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    def _static_analysis(self, code: str) -> Tuple[bool, List[str]]:
        """静态代码分析"""
        issues = []
        
        try:
            tree = ast.parse(code)
            
            # 检查是否有main函数或入口
            has_main = False
            has_if_main = False
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == 'main':
                    has_main = True
                if isinstance(node, ast.If):
                    # 检查 if __name__ == "__main__"
                    if isinstance(node.test, ast.Compare):
                        if hasattr(node.test.left, 'id') and node.test.left.id == '__name__':
                            has_if_main = True
            
            if not has_main and not has_if_main:
                issues.append("建议添加main函数或if __name__ == '__main__'入口")
            
            # 检查是否有异常处理
            has_try = any(isinstance(node, ast.Try) for node in ast.walk(tree))
            if not has_try:
                issues.append("建议添加异常处理(try-except)")
            
            # 检查函数是否有文档字符串
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not ast.get_docstring(node):
                        issues.append(f"函数 {node.name} 缺少文档字符串")
            
            return len(issues) == 0, issues
            
        except Exception as e:
            return False, [str(e)]
    
    async def _fix_code(self, code: str, error: str) -> Optional[str]:
        """使用LLM修复代码"""
        prompt = f"""请修复以下Python代码中的错误。

## 错误信息
{error}

## 原始代码
```python
{code}
```

请直接返回修复后的完整代码，不要包含任何解释。
代码用```python和```包裹。"""

        try:
            response = await self.llm.simple_chat(prompt)
            
            # 提取代码
            import re
            code_pattern = r'```python\n(.*?)```'
            matches = re.findall(code_pattern, response, re.DOTALL)
            
            if matches:
                fixed_code = matches[0]
                # 验证修复后的代码语法
                syntax_ok, _ = self._check_syntax(fixed_code)
                if syntax_ok:
                    logger.info("代码修复成功")
                    return fixed_code
            
            return None
            
        except Exception as e:
            logger.error(f"代码修复失败: {e}")
            return None
    
    async def validate_and_fix(self, code: GeneratedCode) -> GeneratedCode:
        """验证并返回修复后的代码"""
        result = await self._validate_single_code(code)
        
        if result.fixed_code:
            return GeneratedCode(
                task_id=code.task_id,
                file_name=code.file_name,
                code=result.fixed_code,
                description=code.description,
                dependencies=code.dependencies
            )
        
        return code
