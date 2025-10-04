# Copyright (c) Opendatalab. All rights reserved.

import gc

from loguru import logger


def cleanup_vram():
    """清理显存"""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("显存清理完成")
    except ImportError:
        logger.info("PyTorch未安装，跳过显存清理")


def check_vram_available():
    """检查显存是否可用"""
    try:
        import torch
        if torch.cuda.is_available():
            total_memory = torch.cuda.get_device_properties(0).total_memory
            allocated_memory = torch.cuda.memory_allocated(0)
            free_memory = total_memory - allocated_memory
            
            # 单GPU环境，需要至少1.5GB显存才能处理
            required_memory = 1.5 * 1024**3
            is_available = free_memory > required_memory
            
            logger.info(f"显存状态: 总计={total_memory/1024**3:.1f}GB, "
                       f"已分配={allocated_memory/1024**3:.1f}GB, "
                       f"可用={free_memory/1024**3:.1f}GB, "
                       f"可用性={is_available}")
            
            return is_available
    except ImportError:
        logger.info("PyTorch未安装，假设显存可用")
    
    return True  # CPU模式总是可用
