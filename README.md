# 苏绣轮廓生成器

基于计算机视觉的刺绣图案自动化生成工具，可将手稿纹样图转换为机绣格式（DST/ME）。

## 功能特性

- **智能轮廓提取**：自动识别手稿中的线条和图案
- **填充模式**：支持仅轮廓或带填充两种生成模式
- **智能填充检测**：自动判断原图中的填充区域，避免误填充
- **多格式导出**：支持 DST（机绣通用格式）和 ME（HP ME10 CAD）格式
- **可视化预览**：实时预览生成效果
- **精细度调节**：1-100级精细度控制，平衡细节与针数

## 安装

### 环境要求

- Python 3.8+
- 推荐使用 Anaconda 管理环境

### 安装步骤

```bash
# 克隆项目
git clone <repository-url>
cd suzhou_embroidery

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### GUI 模式

```bash
python main.py
```

启动图形界面后：
1. 点击"加载图片"选择手稿图片
2. 调整精细度滑块（1-100）
3. 选择模式：仅轮廓 / 带填充
4. 点击"生成图案"
5. 保存为 DST 或 ME 格式

### 命令行模式

```python
from processor import EmbroideryProcessor

processor = EmbroideryProcessor()
processor.load_image('input.png')
processor.process(detail_level=50, mode='fill')
processor.save_dst('output.dst')
```

## 技术要点

### 图像处理流程

1. **自适应二值化**：处理光照不均的扫描件
2. **骨架化提取**：Zhang-Suen 算法提取线条中心线
3. **智能追踪**：方向一致性优先的骨架追踪算法
4. **Douglas-Peucker 简化**：对数映射精细度控制
5. **自动闭合**：30像素容差的环形路径检测

### 填充算法

- **Tatami 填充**：平行扫描线填充，行间距 2.5 像素
- **智能区域检测**：基于像素密度判断填充区域（30% 阈值）
- **针迹优化**：贪心最近邻排序，最小化跳针距离

### DST 格式规范

- 单位：0.1mm
- 最大针距：12mm（自动拆分）
- 物理尺寸：最长边 200mm，保持宽高比

## 项目结构

```
suzhou_embroidery/
├── processor.py          # 核心处理引擎
├── simple_fill.py        # 填充图案生成
├── me_exporter_fixed.py  # ME 格式导出
├── gui.py                # 图形界面
├── main.py               # 程序入口
└── dst_viewer.py         # DST 文件查看器
```

## 许可证

MIT License
