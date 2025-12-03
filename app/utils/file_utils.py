"""
文件处理工具
"""
import os
import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.schemas.models import DataFileInfo
from app.utils.logger import logger


def get_supported_extensions() -> Dict[str, List[str]]:
    """获取支持的文件扩展名"""
    return {
        "excel": [".xlsx", ".xls"],
        "csv": [".csv"],
        "pdf": [".pdf"],
    }


def detect_file_type(file_path: str) -> Optional[str]:
    """检测文件类型"""
    ext = Path(file_path).suffix.lower()
    extensions = get_supported_extensions()
    
    for file_type, exts in extensions.items():
        if ext in exts:
            return file_type
    return None


def extract_excel_info(file_path: str) -> DataFileInfo:
    """提取Excel文件信息"""
    logger.info(f"提取Excel文件信息: {file_path}")
    
    try:
        # 读取Excel文件
        df = pd.read_excel(file_path)
        
        # 获取样本数据(前5行)
        sample_data = df.head(5).to_dict(orient='records')
        
        return DataFileInfo(
            file_path=file_path,
            file_type="excel",
            file_name=Path(file_path).name,
            columns=df.columns.tolist(),
            row_count=len(df),
            sample_data=sample_data,
            description=f"Excel文件，包含{len(df.columns)}列，{len(df)}行数据"
        )
    except Exception as e:
        logger.error(f"读取Excel文件失败: {e}")
        return DataFileInfo(
            file_path=file_path,
            file_type="excel",
            file_name=Path(file_path).name,
            description=f"读取失败: {str(e)}"
        )


def extract_csv_info(file_path: str, encoding: str = 'utf-8') -> DataFileInfo:
    """提取CSV文件信息"""
    logger.info(f"提取CSV文件信息: {file_path}")
    
    try:
        # 尝试不同编码
        for enc in [encoding, 'gbk', 'gb2312', 'utf-8-sig']:
            try:
                df = pd.read_csv(file_path, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("无法解码CSV文件")
        
        sample_data = df.head(5).to_dict(orient='records')
        
        return DataFileInfo(
            file_path=file_path,
            file_type="csv",
            file_name=Path(file_path).name,
            columns=df.columns.tolist(),
            row_count=len(df),
            sample_data=sample_data,
            description=f"CSV文件，包含{len(df.columns)}列，{len(df)}行数据"
        )
    except Exception as e:
        logger.error(f"读取CSV文件失败: {e}")
        return DataFileInfo(
            file_path=file_path,
            file_type="csv",
            file_name=Path(file_path).name,
            description=f"读取失败: {str(e)}"
        )


def scan_data_files(
    directory: str,
    recursive: bool = True,
    limit: Optional[int] = 50
) -> List[DataFileInfo]:
    """
    扫描目录中的数据文件
    
    Args:
        directory: 需要扫描的目录
        recursive: 是否递归扫描子目录
        limit: 返回的数据文件数量上限（None表示无限制）
    """
    logger.info(f"扫描数据文件目录: {directory}")
    
    data_files: List[DataFileInfo] = []
    
    if not os.path.exists(directory):
        logger.warning(f"目录不存在: {directory}")
        return data_files
    
    walker = os.walk(directory) if recursive else [(directory, [], os.listdir(directory))]
    
    for root, _, files in walker:
        for file_name in files:
            file_path = os.path.join(root, file_name)
            if not os.path.isfile(file_path):
                continue
            
            file_type = detect_file_type(file_path)
            info: Optional[DataFileInfo] = None
            
            if file_type == "excel":
                info = extract_excel_info(file_path)
            elif file_type == "csv":
                info = extract_csv_info(file_path)
            
            if info:
                data_files.append(info)
                if limit and len(data_files) >= limit:
                    logger.warning("数据文件数量达到限制(%s)，停止扫描", limit)
                    return data_files
        
        if not recursive:
            break
    
    logger.info(f"发现 {len(data_files)} 个数据文件")
    return data_files


def create_work_dir(task_id: str, base_dir: str = "output") -> str:
    """创建工作目录"""
    work_dir = os.path.join(base_dir, task_id)
    os.makedirs(work_dir, exist_ok=True)
    logger.info(f"创建工作目录: {work_dir}")
    return work_dir


def save_code_file(work_dir: str, file_name: str, content: str) -> str:
    """保存代码文件"""
    file_path = os.path.join(work_dir, file_name)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"保存代码文件: {file_path}")
    return file_path
