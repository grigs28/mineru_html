# MinerU v0.6.0 发布说明

## 🎉 重大版本更新 - 模块化重构

**发布日期**: 2025年10月4日  
**版本号**: v0.6.0  
**提交哈希**: 0e78562f5705900e8c2fa471aecadb0dcae23d34

---

## 📋 更新概览

这是一个重要的架构重构版本，将原本庞大的单体文件拆分为多个功能明确的模块，大幅提升了代码的可维护性和可扩展性。

### 🏗️ 核心改进

- **代码行数**: 从2269行单体文件拆分为8个独立模块
- **模块化**: 按功能分组组织代码，职责清晰
- **可维护性**: 大幅提升代码可读性和维护效率
- **向后兼容**: 保持所有原有API接口不变

---

## 📁 新增文件结构

```
src/
├── task/                    # 任务管理模块
│   ├── models.py           # 任务模型定义
│   ├── manager.py          # 任务管理器实现
│   └── processor.py        # 任务处理逻辑
├── file/                   # 文件处理模块
│   ├── manager.py          # 文件列表管理
│   ├── handler.py          # 文件处理工具
│   └── pdf_processor.py    # PDF处理功能
└── utils/                  # 工具函数模块
    ├── vram.py            # 显存管理
    └── helpers.py         # 辅助函数
```

---

## 🚀 启动方式

### 推荐方式
```bash
python run_gradio.py --enable-sglang-engine --host 0.0.0.0 --port 7860
```

### 其他方式
```bash
# Shell脚本启动
./start_with_sglang.sh

# 直接运行
python gradio_app.py --enable-sglang-engine --host 0.0.0.0 --port 7860
```

---

## 🧪 测试验证

### 运行测试
```bash
# 完整功能测试
python tests/test_refactoring.py

# 启动测试
python test_startup.py

# 导入问题修复
python fix_imports.py
```

### 测试覆盖
- ✅ 任务模型测试
- ✅ 任务管理器测试
- ✅ 文件管理器测试
- ✅ 显存工具测试
- ✅ 模块导入测试

---

## 📚 文档

- **重构文档**: `docs/REFACTORING_SUMMARY.md`
- **更新日志**: `CHANGELOG.md`
- **发布说明**: `RELEASE_v0.6.0.md`

---

## 🔧 技术细节

### 模块职责

**任务管理模块** (`src/task/`)
- `models.py`: 定义任务状态、队列状态和任务信息数据结构
- `manager.py`: 实现任务创建、更新、查询和队列管理功能
- `processor.py`: 处理后台任务执行逻辑

**文件处理模块** (`src/file/`)
- `manager.py`: 管理服务器端文件列表的加载和保存
- `handler.py`: 提供文件名清理、图片转换等工具函数
- `pdf_processor.py`: 实现PDF解析和处理核心功能

**工具模块** (`src/utils/`)
- `vram.py`: 管理GPU显存的检查和清理
- `helpers.py`: 提供输出目录管理等辅助功能

### 路径问题解决

自动添加项目根目录到Python路径：
```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

---

## 🎯 影响评估

### 正面影响
- ✅ 代码结构更清晰，便于维护和扩展
- ✅ 模块职责单一，提高代码复用性
- ✅ 支持独立开发和测试各个功能模块
- ✅ 解决了大文件难以维护的问题
- ✅ 为后续功能扩展奠定了良好基础

### 兼容性
- ✅ 保持所有原有API接口不变
- ✅ 不影响现有的前端调用
- ✅ 向后兼容，无需修改其他代码

---

## 🔄 迁移指南

### 开发者
- 使用新的模块结构进行开发
- 遵循模块职责分离原则
- 利用新的测试工具验证功能

### 用户
- 推荐使用 `python run_gradio.py` 启动
- 如遇导入问题，运行 `python fix_imports.py` 修复
- 所有原有功能保持不变

---

## 📈 未来规划

基于新的模块化架构，后续版本将能够：
- 更快速地添加新功能
- 更独立地测试和验证各个模块
- 更容易地维护和修复代码
- 更好地支持团队协作开发

---

## 🐛 问题反馈

如遇到任何问题，请：
1. 运行 `python test_startup.py` 检查环境
2. 运行 `python fix_imports.py` 修复导入问题
3. 查看 `docs/REFACTORING_SUMMARY.md` 了解详细说明
4. 提交issue并附上错误日志

---

**感谢使用MinerU！** 🚀
