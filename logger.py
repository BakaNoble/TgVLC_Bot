"""
日志管理系统模块
提供完整的日志记录、文件轮转、存储管理功能
"""
import logging
import os
import re
import json
import shutil
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, List, Dict, Any
import threading
import time

class AdvancedLogger:
    """高级日志管理器"""

    # 最大缓存 logger 数量，防止内存泄漏
    _MAX_LOGGERS: int = 20

    def __init__(
        self,
        log_dir: str = 'logs',
        max_file_size: int = 10 * 1024 * 1024,
        backup_count: int = 10,
        max_storage_days: int = 30,
        max_storage_size: int = 500 * 1024 * 1024
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        self.archive_dir = self.log_dir / 'archive'
        self.archive_dir.mkdir(exist_ok=True)

        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.max_storage_days = max_storage_days
        self.max_storage_size = max_storage_size

        self.json_log_file = self.log_dir / 'bot_logs.json'
        self.last_archive_date = self._load_last_archive_date()
        self.loggers: OrderedDict[str, logging.Logger] = OrderedDict()
        self._lock = threading.RLock()
        self._write_count: int = 0  # 写入计数器，避免频繁检查压缩
        self._last_compact_check: float = 0.0

        self._init_json_log()
        self._check_daily_archive()
        self._cleanup_old_logs()

    def _init_json_log(self):
        """初始化JSON日志文件（行格式）"""
        if not self.json_log_file.exists():
            with open(self.json_log_file, 'w', encoding='utf-8') as f:
                pass  # 创建空文件

    def _format_log_message(self, level: str, module: str, message: str, **kwargs) -> Dict[str, Any]:
        """格式化日志消息"""
        return {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'module': module,
            'message': message,
            'details': kwargs if kwargs else None
        }

    def log(
        self,
        level: str,
        module: str,
        message: str,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        **kwargs
    ):
        """记录日志到JSON文件和系统日志"""
        with self._lock:
            self._check_daily_archive()

            log_entry = self._format_log_message(level, module, message, **kwargs)
            log_entry['user_id'] = user_id
            log_entry['chat_id'] = chat_id

            self._write_json_log(log_entry)

            # 获取 logger 实例（在锁内完成缓存管理）
            logger = self._get_logger(module)

        # Python logger 的 handler 有自己的锁，放在外部锁之外减少 contention
        logger.log(getattr(logging, level), message)

        return log_entry

    def _write_json_log(self, log_entry: Dict[str, Any]):
        """写入JSON日志文件（追加模式，O(1)复杂度）"""
        try:
            with open(self.json_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

            # 基于写入计数检查是否需要压缩（每100次写入检查一次）
            self._write_count += 1
            if self._write_count >= 100:
                self._write_count = 0
                self._check_and_compact()

        except Exception as e:
            print(f"Failed to write JSON log: {e}")

    def _check_and_compact(self):
        """检查并压缩日志文件（当行数超过限制时）"""
        try:
            # 快速估算行数（通过文件大小，假设平均每行200字节）
            file_size = self.json_log_file.stat().st_size
            estimated_lines = file_size // 200

            # 如果估算行数未超过阈值，跳过精确计数
            if estimated_lines < 10000:
                return

            # 精确计数（仅当估算超过阈值时）
            line_count = 0
            with open(self.json_log_file, 'r', encoding='utf-8') as f:
                for _ in f:
                    line_count += 1
                    if line_count > 10050:  # 留50条余量
                        break

            # 如果超过10000条，只保留最新的10000条
            if line_count > 10000:
                self._compact_logs()
        except Exception as e:
            print(f"Failed to check/compact logs: {e}")

    def _compact_logs(self):
        """压缩日志文件，只保留最新的10000条（流式处理，避免全量加载）"""
        try:
            import collections

            # 使用 deque 作为滑动窗口，仅在内存中保留最新的10000条
            retained = collections.deque(maxlen=10000)
            total = 0
            with open(self.json_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    total += 1
                    retained.append(line)

            if total <= 10000:
                return

            # 写回保留的行
            with open(self.json_log_file, 'w', encoding='utf-8') as f:
                f.writelines(retained)

            print(f"Logs compacted: {len(retained)} entries retained (removed {total - len(retained)} old entries)")
        except Exception as e:
            print(f"Failed to compact logs: {e}")

    def _get_logger(self, module: str) -> logging.Logger:
        """获取或创建logger实例（带文件轮转handler，有界缓存）

        使用 OrderedDict 实现 O(1) LRU，当缓存满时移除最久未使用的 logger。
        """
        with self._lock:
            if module in self.loggers:
                self.loggers.move_to_end(module)
                return self.loggers[module]

            # 如果缓存已满，移除最久未使用的 logger
            if len(self.loggers) >= self._MAX_LOGGERS:
                oldest_module, oldest_logger = self.loggers.popitem(last=False)
                self._remove_logger_instance(oldest_logger)

            logger = self._create_logger(module)
            self.loggers[module] = logger
            return logger

    def _create_logger(self, module: str) -> logging.Logger:
        """创建新的 logger 实例"""
        logger = logging.getLogger(f'tgvlc_{module}')
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        log_file = self.log_dir / f'{module}.log'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        return logger

    def _remove_logger_instance(self, logger: logging.Logger) -> None:
        """移除并关闭指定 logger 实例"""
        for handler in logger.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            logger.removeHandler(handler)

    def _load_last_archive_date(self) -> Optional[str]:
        """加载上次归档日期"""
        marker_file = self.log_dir / '.last_archive'
        if marker_file.exists():
            try:
                with open(marker_file, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except:
                pass
        return None

    def _save_last_archive_date(self, date_str: str):
        """保存上次归档日期"""
        marker_file = self.log_dir / '.last_archive'
        try:
            with open(marker_file, 'w', encoding='utf-8') as f:
                f.write(date_str)
        except Exception as e:
            print(f"Failed to save archive date: {e}")

    def _check_daily_archive(self):
        """检查是否需要每日归档"""
        today = datetime.now().strftime('%Y-%m-%d')

        if self.last_archive_date != today:
            self._perform_daily_archive()
            self.last_archive_date = today
            self._save_last_archive_date(today)

    def _perform_daily_archive(self):
        """执行每日归档（行格式版）"""
        try:
            if not self.json_log_file.exists():
                return

            # 读取所有日志
            logs = []
            with open(self.json_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            logs.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

            if not logs:
                return

            archive_date = datetime.now().strftime('%Y%m%d')
            archive_file = self.archive_dir / f'logs_{archive_date}.json'

            # 读取已存在的归档日志
            existing_logs = []
            if archive_file.exists():
                with open(archive_file, 'r', encoding='utf-8') as f:
                    try:
                        existing_logs = json.load(f)
                    except json.JSONDecodeError:
                        existing_logs = []

            existing_logs.extend(logs)

            # 写入归档文件
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump(existing_logs, f, ensure_ascii=False, indent=2)

            # 清空当前日志文件
            with open(self.json_log_file, 'w', encoding='utf-8') as f:
                f.write('')

            print(f"Daily archive completed: {len(logs)} logs archived to {archive_file.name}")

        except Exception as e:
            print(f"Failed to perform daily archive: {e}")

    def get_archived_logs(
        self,
        date: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """获取归档日志"""
        try:
            if date:
                archive_file = self.archive_dir / f'logs_{date}.json'
                if not archive_file.exists():
                    return {
                        'logs': [],
                        'page': page,
                        'limit': limit,
                        'total': 0,
                        'totalPages': 0,
                        'date': date
                    }

                with open(archive_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            else:
                logs = []
                for archive_file in sorted(self.archive_dir.glob('logs_*.json'), reverse=True):
                    with open(archive_file, 'r', encoding='utf-8') as f:
                        try:
                            logs.extend(json.load(f))
                        except json.JSONDecodeError:
                            continue

            logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

            total = len(logs)
            total_pages = (total + limit - 1) // limit
            start = (page - 1) * limit
            end = start + limit

            return {
                'logs': logs[start:end],
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages
            }

        except Exception as e:
            print(f"Failed to get archived logs: {e}")
            return {
                'logs': [],
                'page': page,
                'limit': limit,
                'total': 0,
                'totalPages': 0
            }

    def get_archive_list(self) -> List[str]:
        """获取归档文件列表"""
        try:
            archives = []
            for archive_file in sorted(self.archive_dir.glob('logs_*.json'), reverse=True):
                archives.append(archive_file.name.replace('logs_', '').replace('.json', ''))
            return archives
        except Exception as e:
            print(f"Failed to get archive list: {e}")
            return []

    def _cleanup_old_logs(self):
        """清理过期日志"""
        self._cleanup_by_age()
        self._cleanup_by_size()

    def _cleanup_by_age(self):
        """按时间清理日志"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.max_storage_days)

            # 清理 .log 文件
            for log_file in self.log_dir.iterdir():
                if log_file.is_file() and log_file.suffix == '.log' and log_file.name != 'bot_logs.json':
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff_date:
                        log_file.unlink()

            # 清理 JSON 日志中的过期条目
            if self.json_log_file.exists():
                filtered_logs = []
                with open(self.json_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            log = json.loads(line)
                            if datetime.fromisoformat(log['timestamp']) > cutoff_date:
                                filtered_logs.append(log)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue

                # 重写文件（行格式）
                with open(self.json_log_file, 'w', encoding='utf-8') as f:
                    for log in filtered_logs:
                        f.write(json.dumps(log, ensure_ascii=False) + '\n')

        except Exception as e:
            print(f"Failed to cleanup by age: {e}")

    def _cleanup_by_size(self):
        """按大小清理日志"""
        try:
            _log_backup_pattern = re.compile(r'\.log\.\d+$')
            log_files = [f for f in self.log_dir.iterdir()
                         if f.is_file() and (f.suffix == '.log' or _log_backup_pattern.search(f.name))]
            total_size = sum(f.stat().st_size for f in log_files)

            if total_size > self.max_storage_size:
                files = sorted(
                    log_files,
                    key=lambda f: f.stat().st_mtime
                )

                for log_file in files:
                    if total_size <= self.max_storage_size * 0.8:
                        break
                    total_size -= log_file.stat().st_size
                    log_file.unlink()

        except Exception as e:
            print(f"Failed to cleanup by size: {e}")

    def get_logs(
        self,
        page: int = 1,
        limit: int = 20,
        level: Optional[str] = None,
        module: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """获取日志列表"""
        try:
            if not self.json_log_file.exists():
                return {
                    'logs': [],
                    'page': page,
                    'limit': limit,
                    'total': 0,
                    'totalPages': 0
                }

            # 收集并过滤日志
            filtered_logs = []

            with open(self.json_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log = json.loads(line)

                        # 应用过滤器
                        if level and log.get('level') != level.upper():
                            continue
                        if module and log.get('module') != module:
                            continue
                        if search and search.lower() not in log.get('message', '').lower():
                            continue
                        if date_from and log.get('timestamp', '') < date_from:
                            continue
                        if date_to and log.get('timestamp', '') > date_to:
                            continue
                        if user_id and log.get('user_id') != user_id:
                            continue

                        filtered_logs.append(log)
                    except json.JSONDecodeError:
                        continue

            # 排序（最新在前）
            filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

            total = len(filtered_logs)
            total_pages = (total + limit - 1) // limit if total > 0 else 1
            start = (page - 1) * limit
            end = start + limit

            page_logs = filtered_logs[start:end]
            for i, log in enumerate(page_logs):
                log['id'] = start + i + 1

            return {
                'logs': page_logs,
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': total_pages
            }

        except Exception as e:
            print(f"Failed to get logs: {e}")
            return {
                'logs': [],
                'page': page,
                'limit': limit,
                'total': 0,
                'totalPages': 0
            }

    def get_stats(self) -> Dict[str, Any]:
        """获取日志统计（单次扫描O(n)）"""
        try:
            if not self.json_log_file.exists():
                return {
                    'total': 0,
                    'today': 0,
                    'levelCounts': {},
                    'moduleCounts': {},
                    'userOperations': 0,
                    'scriptOperations': 0
                }

            level_counts = {}
            module_counts = {}
            user_operations = 0
            script_operations = 0
            total = 0
            today = datetime.now().strftime('%Y-%m-%d')
            today_count = 0

            with open(self.json_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        log = json.loads(line)
                        total += 1

                        level = log.get('level', 'INFO')
                        level_counts[level] = level_counts.get(level, 0) + 1

                        module = log.get('module', 'main')
                        module_counts[module] = module_counts.get(module, 0) + 1

                        if log.get('user_id'):
                            user_operations += 1
                        else:
                            script_operations += 1

                        if log.get('timestamp', '').startswith(today):
                            today_count += 1
                    except json.JSONDecodeError:
                        continue

            return {
                'total': total,
                'today': today_count,
                'levelCounts': level_counts,
                'moduleCounts': module_counts,
                'userOperations': user_operations,
                'scriptOperations': script_operations
            }

        except Exception as e:
            print(f"Failed to get stats: {e}")
            return {
                'total': 0,
                'today': 0,
                'levelCounts': {},
                'moduleCounts': {},
                'userOperations': 0,
                'scriptOperations': 0
            }

    def export_logs(
        self,
        format: str = 'json',
        level: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> str:
        """导出日志"""
        logs = self.get_logs(
            page=1,
            limit=10000,
            level=level,
            date_from=date_from,
            date_to=date_to
        )['logs']

        if format == 'csv':
            return self._export_csv(logs)
        else:
            return self._export_json(logs)

    def _export_json(self, logs: List[Dict]) -> str:
        """导出为JSON格式"""
        export_file = self.log_dir / f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        return str(export_file)

    def _export_csv(self, logs: List[Dict]) -> str:
        """导出为CSV格式"""
        import csv

        export_file = self.log_dir / f'export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        with open(export_file, 'w', newline='', encoding='utf-8-sig') as f:
            if logs:
                fieldnames = ['timestamp', 'level', 'module', 'message', 'user_id', 'chat_id']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for log in logs:
                    row = {k: log.get(k, '') for k in fieldnames}
                    if log.get('details'):
                        row['message'] += f" | {json.dumps(log['details'])}"
                    writer.writerow(row)

        return str(export_file)

    def clear_logs(self):
        """清空所有日志"""
        with self._lock:
            # 先关闭所有 handler 以释放文件锁
            for module_logger in self.loggers.values():
                for handler in module_logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler):
                        handler.close()
                    module_logger.removeHandler(handler)
            self.loggers.clear()

            # 删除 .log 文件
            for log_file in self.log_dir.iterdir():
                if log_file.is_file() and log_file.suffix == '.log' and log_file.name != 'bot_logs.json':
                    try:
                        log_file.unlink()
                    except PermissionError:
                        pass  # Windows 下文件可能仍被占用

            # 清空 JSON 日志文件
            with open(self.json_log_file, 'w', encoding='utf-8') as f:
                pass

    def shutdown(self) -> None:
        """优雅关闭日志系统，flush 并关闭所有 handler

        推荐在程序退出前调用此方法，确保所有日志都已写入磁盘。
        """
        with self._lock:
            for module_logger in self.loggers.values():
                for handler in module_logger.handlers[:]:
                    try:
                        handler.flush()
                        handler.close()
                    except Exception as e:
                        print(f"Error closing handler: {e}")
                    module_logger.removeHandler(handler)
            self.loggers.clear()
            print("Logger shutdown complete")

    def __enter__(self) -> 'AdvancedLogger':
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器退出，自动调用 shutdown"""
        self.shutdown()
        return False  # 不抑制异常

    def info(self, module: str, message: str, **kwargs):
        """记录INFO级别日志"""
        return self.log('INFO', module, message, **kwargs)

    def debug(self, module: str, message: str, **kwargs):
        """记录DEBUG级别日志"""
        return self.log('DEBUG', module, message, **kwargs)

    def warning(self, module: str, message: str, **kwargs):
        """记录WARNING级别日志"""
        return self.log('WARNING', module, message, **kwargs)

    def error(self, module: str, message: str, **kwargs):
        """记录ERROR级别日志"""
        return self.log('ERROR', module, message, **kwargs)


advanced_logger = AdvancedLogger()
