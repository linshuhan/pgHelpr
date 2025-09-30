import asyncio
import hashlib
import random
import sys
import time
import os
from typing import Final, List, Dict, Tuple, Optional
from urllib.parse import urlparse
from dataclasses import dataclass

import httpx
from httpx import URL
from loguru import logger

# 配置常量
TOKEN_FILE_PATH: Final[str] = "token.txt"
CONFIG_FILE_PATH: Final[str] = "config.txt"
APP_VERSION: Final[str] = "1.82.1"
APP_SECRET: Final[str] = "nFU9pbG8YQoAe1kFh+E7eyrdlSLglwEJeA0wwHB1j5o="
ALIPAY_APP_SECRET: Final[str] = "Ew+ZSuppXZoA9YzBHgHmRvzt0Bw1CpwlQQtSl49QNhY="

# 任务配置
TASKS: Final[List[str]] = [
    "bd28f4af-44d6-4920-8e34-51b42a07960c",
    "c48ebae8-4c11-490e-8ec0-570053dcb020",
    "90a0dceb-8b89-4c5a-b08d-60cf43b9a0c8",
    "02388d14-3ab5-43fc-b709-108b371fb6d8",
    "d798d2e3-7c16-4b5d-9e6d-4b8214ebf2e5",
    "7",
    "c6fee3bc-84ba-4090-9303-2fbf207b2bbd",
    "5",
    "2",
]

ALIPAY_TASKS: Final[List[str]] = ["9"]

# 运行模式
class RunMode:
    FULL = 1  # 全自动化
    NO_APP_TASKS = 2  # 禁用胖乖APP任务运行，仅签到和小程序
    ONLY_CHECKIN = 3  # 仅运行签到任务

@dataclass
class AccountConfig:
    """账号配置类"""
    token: str
    phone_brand: str
    enabled: bool = True
    delay_min: int = 0
    delay_max: int = 0

class PgAccount:
    def __init__(self, token: str, phone_brand: str):
        self.client = httpx.AsyncClient(
            base_url="https://userapi.qiekj.com",
            event_hooks={"request": [self._request_hook]},
            timeout=30.0,  # 添加超时设置
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        self.token = token
        self.phone_brand = phone_brand
        self.username: Optional[str] = None

    @classmethod
    async def create(cls, token: str, phone_brand: str):
        self = cls(token, phone_brand)
        await self._get_acw_tc()
        # 初始化时获取用户名
        self.username = await self.get_user_name()
        return self

    def get_sign(
        self, request_url: str | URL, timestamp: str | int, channel="android_app"
    ) -> str:
        """
        获取某个请求的 sign
        """
        parsed_url = urlparse(str(request_url))
        path = parsed_url.path
        
        if channel.lower() == "android_app":
            signature_string = f"appSecret={APP_SECRET}&channel={channel}&timestamp={str(timestamp)}&token={self.token}&version={APP_VERSION}&{path}"
        elif channel.lower() == "alipay":
            signature_string = f"appSecret={ALIPAY_APP_SECRET}&channel={channel.lower()}&timestamp={str(timestamp)}&token={self.token}&{path}"
        else:
            raise ValueError(f"Unknown channel: {channel}")
            
        return hashlib.sha256(signature_string.encode("utf-8")).hexdigest()

    async def get_balance(self) -> Dict:
        """获取账户余额"""
        try:
            _data = {"token": self.token}
            response = await self.client.post("/user/balance", data=_data)
            response.raise_for_status()
            response_json = response.json()
            
            if response_json.get("code") != 0:
                raise Exception(f"API返回错误: {response_json.get('message')}")
                
            return response_json["data"]
        except httpx.RequestError as e:
            raise Exception(f"网络请求失败: {e}")
        except KeyError as e:
            raise Exception(f"解析响应数据失败: {e}")

    async def _get_acw_tc(self):
        """获取acw_tc cookie"""
        try:
            _data = {"slotKey": "android_open_screen_1_35_0", "token": self.token}
            response = await self.client.post("/slot/get", data=_data)
            response.raise_for_status()
            return response.headers.get("Set-Cookie", "").split(";")[0]
        except Exception as e:
            logger.warning(f"获取acw_tc失败: {e}")
            return ""

    async def _request_hook(self, request: httpx.Request):
        """请求钩子，添加签名和headers"""
        timestamp = str(int(time.time() * 1000))
        
        request.headers.update({
            "User-Agent": "okhttp/4.12.0",
            "Accept-Encoding": "gzip",
            "Version": APP_VERSION,
            "phoneBrand": self.phone_brand,
            "Authorization": self.token,
            "timestamp": timestamp,
        })

        channel = request.extensions.get("channel", "android_app")
        if channel == "alipay":
            request.headers["sign"] = self.get_sign(request.url, timestamp, "alipay")
            request.headers["channel"] = "alipay"
            request.headers.pop("Version", None)
            request.headers.pop("phoneBrand", None)
        else:
            request.headers["sign"] = self.get_sign(request.url, timestamp)
            request.headers["channel"] = "android_app"

    async def complete_task(self, task_code: str, channel="android_app") -> bool:
        """完成任务"""
        try:
            _data = {"taskCode": task_code, "token": self.token}
            response = await self.client.post(
                url="/task/completed", 
                data=_data, 
                extensions={"channel": channel}
            )
            response.raise_for_status()
            response_json = response.json()
            
            return response_json.get("code") == 0 and response_json.get("data") is True
        except Exception as e:
            logger.error(f"完成任务失败: {e}")
            return False

    async def is_captcha(self) -> bool:
        """检查是否触发人机验证"""
        try:
            _data = {"token": self.token}
            response = await self.client.post(url="/integralCaptcha/isCaptcha", data=_data)
            response.raise_for_status()
            return False
        except Exception as e:
            if "人机验证" in str(e):
                return True
            raise e

    async def get_task_list(self, channel="android_app") -> List[Dict]:
        """获取任务列表"""
        try:
            _data = {"token": self.token}
            response = await self.client.post(
                url="task/list", 
                data=_data, 
                extensions={"channel": channel}
            )
            response.raise_for_status()
            response_json = response.json()
            
            if response_json.get("code") != 0:
                raise Exception(f"获取任务列表失败: {response_json.get('message')}")
                
            return response_json["data"]["items"]
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return []

    async def checkin(self) -> bool:
        """签到"""
        try:
            _data = {"activityId": "600001", "token": self.token}
            response = await self.client.post(url="/signin/doUserSignIn", data=_data)
            response.raise_for_status()
            response_json = response.json()
            
            if response_json.get("code") == 0:
                return True
            else:
                logger.warning(f"签到失败: {response_json.get('message')}")
                return False
        except Exception as e:
            logger.error(f"签到请求失败: {e}")
            return False

    async def get_user_name(self) -> str:
        """获取用户名"""
        try:
            data = {"token": self.token}
            response = await self.client.post("/user/info", data=data)
            response.raise_for_status()
            res_json = response.json()
            
            if res_json.get("code") != 0:
                return "未知用户"
                
            user_name = res_json["data"].get("userName")
            return user_name if user_name else "未设置昵称"
        except Exception:
            return "未知用户"

def read_accounts_from_file(file_path: str) -> List[AccountConfig]:
    """
    从文件读取账号信息
    文件格式：每行一个账号，格式为 token:phone_brand[:enabled:delay_min:delay_max]
    """
    accounts = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):  # 忽略空行和注释行
                    parts = line.split(':')
                    if len(parts) >= 2:
                        token = parts[0].strip()
                        phone_brand = parts[1].strip()
                        
                        # 解析可选参数
                        enabled = True
                        delay_min = 0
                        delay_max = 0
                        
                        if len(parts) >= 3:
                            enabled = parts[2].strip().lower() not in ['false', '0', 'no']
                        if len(parts) >= 4:
                            try:
                                delay_min = int(parts[3].strip())
                            except ValueError:
                                pass
                        if len(parts) >= 5:
                            try:
                                delay_max = int(parts[4].strip())
                            except ValueError:
                                pass
                                
                        accounts.append(AccountConfig(
                            token=token,
                            phone_brand=phone_brand,
                            enabled=enabled,
                            delay_min=delay_min,
                            delay_max=delay_max
                        ))
                    else:
                        # 如果只有token没有手机品牌，使用默认手机品牌
                        if len(parts) == 1 and parts[0].strip():
                            token = parts[0].strip()
                            logger.warning(f"第{line_num}行缺少手机品牌，使用默认值: Android")
                            accounts.append(AccountConfig(
                                token=token,
                                phone_brand="Android",
                                enabled=True,
                                delay_min=0,
                                delay_max=0
                            ))
                        else:
                            logger.warning(f"第{line_num}行格式错误，已跳过: {line}")
                        
        logger.info(f"从文件 {file_path} 读取到 {len(accounts)} 个账号")
    except FileNotFoundError:
        logger.error(f"文件 {file_path} 不存在")
    except Exception as e:
        logger.error(f"读取文件时出错: {e}")
    
    return accounts

def get_run_mode() -> int:
    """获取用户选择的运行模式"""
    print("\n" + "="*50)
    print("请选择运行模式:")
    print("1. 全自动化（运行所有任务）（作者水印：第四季2248850736）")
    print("2. 禁用胖乖APP任务运行，仅签到和小程序任务")
    print("3. 仅运行签到任务")
    print("="*50)
    
    while True:
        try:
            choice = input("请输入选择 (1/2/3): ").strip()
            if choice in ['1', '2', '3']:
                mode = int(choice)
                mode_names = {
                    RunMode.FULL: "全自动化模式",
                    RunMode.NO_APP_TASKS: "禁用APP任务模式", 
                    RunMode.ONLY_CHECKIN: "仅签到模式"
                }
                print(f"\n已选择: {mode_names[mode]}")
                return mode
            else:
                print("输入无效，请重新输入 1、2 或 3")
        except KeyboardInterrupt:
            print("\n用户取消操作")
            sys.exit(0)
        except Exception as e:
            print(f"输入错误: {e}")

async def process_single_account(account_config: AccountConfig, run_mode: int):
    """处理单个账号"""
    if not account_config.enabled:
        logger.info(f"账号已禁用，跳过处理")
        return
        
    # 随机延迟
    if account_config.delay_max > account_config.delay_min:
        delay = random.randint(account_config.delay_min, account_config.delay_max)
        logger.info(f"随机延迟 {delay} 秒后开始处理")
        await asyncio.sleep(delay)
    
    try:
        account = await PgAccount.create(account_config.token, account_config.phone_brand)
        # 使用绑定了用户名的logger
        user_logger = logger.bind(username=account.username)
        
        user_logger.info(f"开始处理账号 (模式: {run_mode})")
        
        # 显示余额
        try:
            balance_dict = await account.get_balance()
            user_logger.info(f"当前通用小票: {int(balance_dict['tokenCoin']) / 100}")
            user_logger.info(f"当前积分: {balance_dict['integral']}")
        except Exception as e:
            user_logger.warning(f"获取余额失败: {e}")
        
        # 处理签到
        await process_checkin(account, user_logger)
        
        # 根据模式执行任务
        if run_mode == RunMode.FULL:
            # 全自动化：执行所有任务
            await process_app_tasks(account, user_logger)
            await process_miniprogram_tasks(account, user_logger)
        elif run_mode == RunMode.NO_APP_TASKS:
            # 禁用APP任务：只执行小程序任务
            await process_miniprogram_tasks(account, user_logger)
        elif run_mode == RunMode.ONLY_CHECKIN:
            # 仅签到：不执行任何任务
            user_logger.info("仅签到模式，跳过所有任务")
        else:
            user_logger.error(f"未知的运行模式: {run_mode}")
        
        # 显示最终余额
        try:
            balance_dict = await account.get_balance()
            user_logger.success(f"任务完成，当前积分: {balance_dict['integral']}")
        except Exception as e:
            user_logger.warning(f"获取最终余额失败: {e}")
            
    except Exception as e:
        logger.error(f"处理账号时发生错误: {e}")

async def process_checkin(account: PgAccount, user_logger):
    """处理签到"""
    user_logger.info("尝试签到")
    
    # 检查人机验证
    if await handle_captcha(account, user_logger, "签到"):
        await asyncio.sleep(random.random())
        if await account.checkin():
            user_logger.success("签到成功")
        else:
            user_logger.error("签到失败")
    else:
        user_logger.error("无法绕过人机验证，跳过签到")

async def process_app_tasks(account: PgAccount, user_logger):
    """处理APP任务"""
    user_logger.info("开始胖乖生活APP任务")
    
    tasks = await account.get_task_list()
    if not tasks:
        user_logger.warning("未获取到APP任务列表")
        return
        
    await process_tasks(account, tasks, TASKS, "android_app", user_logger)
    user_logger.info("胖乖生活APP任务结束")

async def process_miniprogram_tasks(account: PgAccount, user_logger):
    """处理小程序任务"""
    user_logger.info("开始胖乖生活小程序任务")
    
    tasks = await account.get_task_list(channel="alipay")
    if not tasks:
        user_logger.warning("未获取到小程序任务列表")
        return
        
    await process_tasks(account, tasks, ALIPAY_TASKS, "alipay", user_logger)
    user_logger.info("胖乖生活小程序任务结束")

async def process_tasks(account: PgAccount, tasks: List[Dict], target_tasks: List[str], 
                       channel: str, user_logger):
    """处理任务列表"""
    for task in tasks:
        if (task["taskCode"] in target_tasks and 
            task["completedStatus"] == 0 and 
            task["completedFreq"] is not None):
            
            remaining_times = task["dailyTaskLimit"] - task["completedFreq"]
            if remaining_times <= 0:
                continue
                
            user_logger.info(f"开始处理任务: {task['title']} (剩余{remaining_times}次)")
            
            for num in range(1, remaining_times + 1):
                user_logger.info(f"尝试完成第 {num} 次 {task['title']}")
                
                if await handle_captcha(account, user_logger, f"任务{num}"):
                    await asyncio.sleep(random.randint(45, 55))
                    
                    if await account.complete_task(task["taskCode"], channel):
                        user_logger.success(f"成功完成第 {num} 次 {task['title']}")
                        await asyncio.sleep(random.randint(35, 95))
                    else:
                        user_logger.error(f"完成第 {num} 次 {task['title']} 失败")
                        break
                else:
                    user_logger.error(f"无法绕过人机验证，跳过任务 {task['title']}")
                    break

async def handle_captcha(account: PgAccount, user_logger, operation: str) -> bool:
    """处理人机验证"""
    for i in range(1, 4):
        try:
            if await account.is_captcha():
                if i == 3:
                    user_logger.error(f"{operation} - 无法绕过人机验证")
                    return False
                user_logger.warning(f"{operation} - 触发人机验证，第 {i} 次重试")
                await asyncio.sleep(random.randint(65, 125))
            else:
                return True
        except Exception as e:
            user_logger.warning(f"{operation} - 检查验证时出错: {e}")
            await asyncio.sleep(random.randint(65, 125))
    
    return False

async def main():
    """主函数"""
    # 获取用户选择的运行模式
    run_mode = get_run_mode()
    
    # 从文件读取账号信息
    accounts = read_accounts_from_file(TOKEN_FILE_PATH)
    
    if not accounts:
        logger.error("未找到有效的账号信息，程序退出")
        return
    
    # 过滤启用的账号
    enabled_accounts = [acc for acc in accounts if acc.enabled]
    if not enabled_accounts:
        logger.error("没有启用的账号，程序退出")
        return
        
    logger.info(f"找到 {len(enabled_accounts)} 个启用账号")
    
    # 创建并执行任务
    tasks = []
    for account_config in enabled_accounts:
        task = asyncio.create_task(process_single_account(account_config, run_mode))
        tasks.append(task)
        # 避免同时启动所有任务
        await asyncio.sleep(random.randint(1, 3))
    
    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 检查执行结果
    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        logger.warning(f"{len(errors)} 个账号处理过程中出现错误")

def setup_logging():
    """设置日志配置"""
    logger.remove()
    
    # 配置默认的extra值，避免缺少username字段
    logger.configure(extra={"username": "SYSTEM"})
    
    # 控制台输出
    logger.add(
        sink=sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{extra[username]: <15}</cyan> | "
               "<level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    
    # 文件输出
    log_file = f"logs/pangguai_{time.strftime('%Y%m%d')}.log"
    os.makedirs("logs", exist_ok=True)
    logger.add(
        sink=log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[username]: <15} | {message}",
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
    )

if __name__ == "__main__":
    # 设置日志
    setup_logging()
    
    # 检查文件是否存在
    if not os.path.exists(TOKEN_FILE_PATH):
        logger.error(f"token文件不存在: {TOKEN_FILE_PATH}")
        logger.info("请创建token.txt文件并按照以下格式添加账号:")
        logger.info("格式: token:phone_brand[:enabled:delay_min:delay_max]")
        logger.info("示例: abc123:小米手机:true:0:60")
        logger.info("当前工作目录: " + os.getcwd())
        sys.exit(1)
    
    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")