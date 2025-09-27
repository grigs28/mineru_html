# 单GPU环境多PDF文件处理解决方案

## 🎯 问题解决

针对您只有1个GPU的环境，我已经实施了完整的解决方案来解决"只能处理1个PDF文件，后续文件全部失败"的问题。

## 🔧 已实施的修复

### 1. 增加Docker内存限制
- **内存限制**：从4GB增加到16GB
- **CPU核心**：从2核增加到4核
- **显存限制**：设置为6GB（适合单GPU环境）
- **设备模式**：指定为`cuda:0`

### 2. 修复队列处理逻辑
- **避免队列过早停止**：队列为空时等待新任务而不是停止
- **避免重复启动**：优化任务添加逻辑，防止重复启动队列协程
- **持续处理**：支持多文件连续处理

### 3. 添加显存管理机制
- **显存检查**：处理前检查显存可用性
- **显存清理**：任务完成后自动清理显存
- **显存监控**：详细的显存使用日志

### 4. 创建启动脚本
- **直接启动脚本**：`start_with_sglang.sh`
- **Docker启动脚本**：`docker-start.sh`

## 🚀 使用方法

### 方法1：使用Docker（推荐）

```bash
# 1. 进入项目目录
cd /opt/webapp/mineru_html

# 2. 运行Docker启动脚本
./docker-start.sh
```

### 方法2：直接启动

```bash
# 1. 进入项目目录
cd /opt/webapp/mineru_html

# 2. 运行启动脚本
./start_with_sglang.sh
```

### 方法3：手动启动

```bash
# 设置环境变量
export MINERU_DEVICE_MODE=cuda:0
export MINERU_VIRTUAL_VRAM_SIZE=6000

# 启动服务
python gradio_app.py --enable-sglang-engine --host 0.0.0.0 --port 7860
```

## 📋 测试步骤

### 1. 启动服务
```bash
./docker-start.sh
```

### 2. 监控显存使用
```bash
# 在另一个终端监控GPU显存
nvidia-smi -l 1
```

### 3. 测试多文件处理
1. 访问 http://localhost:7860
2. 上传5个PDF文件
3. 点击"开始转换"
4. 观察所有文件是否都能成功处理

### 4. 验证队列功能
- 第一个文件处理时，后续文件应显示"队列中"状态
- 第一个文件完成后，第二个文件应自动开始处理
- 所有文件应能连续处理完成

## 🔍 预期结果

### ✅ 成功指标
- 所有PDF文件都能成功处理
- 显存使用稳定，无累积增长
- 队列持续运行，不会过早停止
- 处理性能提升

### 📊 显存使用模式
```
任务1: 加载模型 → 处理 → 清理显存
任务2: 复用模型 → 处理 → 清理显存
任务3: 复用模型 → 处理 → 清理显存
...
```

## 🛠️ 故障排除

### 问题1：显存不足
```bash
# 检查显存使用
nvidia-smi

# 如果显存不足，可以调整限制
export MINERU_VIRTUAL_VRAM_SIZE=4000  # 降低到4GB
```

### 问题2：服务启动失败
```bash
# 查看容器日志
docker-compose logs -f

# 重启容器
docker-compose restart
```

### 问题3：队列不工作
```bash
# 检查队列状态
curl http://localhost:7860/api/queue_status

# 手动启动队列
curl -X POST http://localhost:7860/api/start_queue
```

## 📈 性能优化建议

### 1. 显存优化
- 根据实际GPU显存调整`MINERU_VIRTUAL_VRAM_SIZE`
- 监控显存使用，避免碎片化

### 2. 内存优化
- 根据系统内存调整Docker内存限制
- 避免同时运行其他GPU密集型应用

### 3. 队列优化
- 避免同时上传过多文件
- 建议一次处理3-5个文件

## 🎯 关键改进点

1. **模型复用**：启用SgLang Engine，避免重复加载模型
2. **显存管理**：自动清理显存，防止累积占用
3. **队列持续**：修复队列过早停止问题
4. **单GPU优化**：针对单GPU环境进行配置优化

## 📞 支持

如果遇到问题，请：
1. 查看容器日志：`docker-compose logs -f`
2. 检查显存使用：`nvidia-smi`
3. 验证服务状态：访问 http://localhost:7860

这个解决方案应该能够彻底解决您的多PDF文件处理问题！
