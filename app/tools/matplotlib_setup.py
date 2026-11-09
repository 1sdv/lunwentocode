"""
Matplotlib 引导脚本 - 在 Jupyter 内核启动时注入中文字体与绘图常量

参考 MathModelAgent 的 matplotlib_setup：注册中文字体、统一 rcParams、
注入 COLORS / FIG_* 常量，Coder 生成的绘图代码直接使用这些常量。
"""
from __future__ import annotations

# 统一配色方案
COLORS: dict[str, str] = {
    "primary": "#2E5B88",
    "secondary": "#E85D4C",
    "tertiary": "#4A9B7F",
    "neutral": "#7F7F7F",
    "light": "#B8D4E8",
}

FIG_SINGLE = (5, 4)
FIG_DOUBLE = (10, 4)
FIG_WIDE = (8, 3)
FIG_SQUARE = (6, 6)


def build_matplotlib_init_code(
    work_dir: str,
    *,
    font_dir: str | None = None,
    setup_chdir: bool = True,
) -> str:
    """生成在 Jupyter kernel 中执行的 matplotlib 初始化代码。

    Args:
        work_dir: 任务工作目录（用于 chdir 与字体扫描）。
        font_dir: 字体文件目录，默认与 work_dir 相同。
        setup_chdir: 是否切换到 work_dir。

    Returns:
        可在 kernel 中执行的 Python 代码字符串。
    """
    font_dir = font_dir or work_dir

    # 必须先解析为绝对路径：相对路径在 os.chdir 之后会导致 listdir/addfont 失败
    chdir_block = (
        "import os\n"
        f"work_dir = os.path.abspath(r'{work_dir}')\n"
        f"_font_dir = os.path.abspath(r'{font_dir}')\n"
    )
    if setup_chdir:
        chdir_block += (
            "os.makedirs(work_dir, exist_ok=True)\n"
            "os.chdir(work_dir)\n"
            "print('[matplotlib_setup] 当前工作目录:', os.getcwd())\n"
        )

    return (
        chdir_block
        + "import matplotlib\n"
        + "import matplotlib.pyplot as plt\n"
        + "from matplotlib import font_manager\n"
        + "import glob as _glob, pathlib as _pl\n"
        + "_cache_dir = _pl.Path(matplotlib.get_cachedir())\n"
        + "for _cache_file in _glob.glob(str(_cache_dir / 'fontlist*.json')):\n"
        + "    _pl.Path(_cache_file).unlink(missing_ok=True)\n"
        + "font_manager.fontManager.__init__()\n"
        + "_cjk_fonts = []\n"
        + "for _f in os.listdir(_font_dir):\n"
        + "    if _f.lower().endswith(('.ttf', '.otf', '.ttc')):\n"
        + "        _fp = os.path.join(_font_dir, _f)\n"
        + "        font_manager.fontManager.addfont(_fp)\n"
        + "        _name = font_manager.FontProperties(fname=_fp).get_name()\n"
        + "        if _name not in _cjk_fonts:\n"
        + "            _cjk_fonts.append(_name)\n"
        + "if _cjk_fonts:\n"
        + "    CJK_FONT = _cjk_fonts[0]\n"
        + "    _fallback = ['SimHei', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'sans-serif']\n"
        + "    plt.rcParams['font.sans-serif'] = _cjk_fonts + [f for f in _fallback if f not in _cjk_fonts]\n"
        + "    plt.rcParams['axes.unicode_minus'] = False\n"
        + "    plt.rcParams['font.family'] = 'sans-serif'\n"
        + "    print(f'[matplotlib_setup] 中文字体已加载: {CJK_FONT} (共 {len(_cjk_fonts)} 个)')\n"
        + "else:\n"
        + "    CJK_FONT = None\n"
        + "    _fallback = ['SimHei', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'sans-serif']\n"
        + "    plt.rcParams['font.sans-serif'] = _fallback\n"
        + "    plt.rcParams['axes.unicode_minus'] = False\n"
        + "    print('[matplotlib_setup] 警告: 未找到字体文件，使用系统回退字体，中文标签可能显示为方框')\n"
        + "plt.rcParams.update({\n"
        + "    'font.size': 11,\n"
        + "    'axes.titlesize': 12,\n"
        + "    'axes.titleweight': 'bold',\n"
        + "    'axes.labelsize': 11,\n"
        + "    'axes.linewidth': 1.2,\n"
        + "    'axes.spines.top': False,\n"
        + "    'axes.spines.right': False,\n"
        + "    'xtick.labelsize': 10,\n"
        + "    'ytick.labelsize': 10,\n"
        + "    'legend.fontsize': 10,\n"
        + "    'legend.frameon': False,\n"
        + "    'figure.dpi': 300,\n"
        + "    'savefig.dpi': 300,\n"
        + "    'savefig.bbox': 'tight',\n"
        + "    'savefig.pad_inches': 0.1,\n"
        + "})\n"
        + f"COLORS = {COLORS!r}\n"
        + "DEFAULT_COLORS = list(COLORS.values())\n"
        + f"FIG_SINGLE = {FIG_SINGLE!r}\n"
        + f"FIG_DOUBLE = {FIG_DOUBLE!r}\n"
        + f"FIG_WIDE = {FIG_WIDE!r}\n"
        + f"FIG_SQUARE = {FIG_SQUARE!r}\n"
        + "print('[matplotlib_setup] 绘图环境就绪 (COLORS, FIG_* 已注入)')\n"
    )
