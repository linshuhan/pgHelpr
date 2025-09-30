import requests
import json
import time
import hashlib

def sha256_encrypt(data):
    sha256 = hashlib.sha256()
    sha256.update(data.encode("utf-8"))
    return sha256.hexdigest()

def sign(t, url, data_str=""):
    """生成签名"""
    base_str = f"appSecret=nFU9pbG8YQoAe1kFh+E7eyrdlSLglwEJeA0wwHB1j5o=&channel=android_app&timestamp={t}&version=1.60.3&{data_str}"
    return sha256_encrypt(base_str)

def get_token_fixed(phone):
    """获取token函数"""
    print(f"正在为手机号 {phone} 获取token...")
    
    # 一：发送验证码
    send_code_url = "https://userapi.qiekj.com/common/sms/sendCode"
    t = str(int(time.time() * 1000))
    
    headers = {
        "Version": "1.60.3",  # 更新版本号
        "channel": "android_app",
        "phoneBrand": "Redmi", 
        "timestamp": t,
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Host": "userapi.qiekj.com",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; Redmi Note 11 Pro Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/100.0.4896.58 Mobile Safari/537.36",
    }
    
    data = {"phone": phone, "template": "reg"}
    
    try:
        print("📤 发送验证码请求...")
        response = requests.post(send_code_url, headers=headers, data=data, timeout=10)
        result = response.json()
        print(f"发送验证码响应: {result}")
        
        if result.get("code") == 0:
            verify_code = input("✅ 验证码已发送，请输入收到的验证码: ").strip()
            
            # 二：注册获取token
            reg_url = "https://userapi.qiekj.com/user/reg"
            reg_data = {"channel": "android_app", "phone": phone, "verify": verify_code}
            
            # 可能需要为注册请求也生成签名
            t2 = str(int(time.time() * 1000))
            headers["timestamp"] = t2
            
            print("📤 提交验证码注册...")
            reg_response = requests.post(reg_url, headers=headers, data=reg_data, timeout=10)
            reg_result = reg_response.json()
            print(f"注册响应: {reg_result}")
            
            if reg_result.get("code") == 0 and "data" in reg_result and "token" in reg_result["data"]:
                token = reg_result["data"]["token"]
                print(f"🎉 成功获取token: {token}")
                
                # 保存token
                with open("token.txt", "w") as f:
                    f.write(token)
                print("✅ token已保存到 token.txt")
                return token
            else:
                print(f"❌ 注册失败: {reg_result.get('msg', '未知错误')}")
                return None
        else:
            print(f"❌ 发送验证码失败: {result.get('msg', '未知错误')}")
            # 显示具体错误信息
            if result.get("code") == 40001:
                print("⚠️  请求过于频繁，请等待几分钟再试")
            elif result.get("code") == 40002:
                print("⚠️  手机号格式错误")
            elif result.get("code") == 40003:
                print("⚠️  该手机号已注册")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时，请检查网络连接")
        return None
    except requests.exceptions.ConnectionError:
        print("❌ 网络连接错误，请检查网络")
        return None
    except Exception as e:
        print(f"❌ 发生未知错误: {e}")
        return None

def debug_current_status():
    """调试当前状态"""
    print("\n🔍 调试信息:")
    if os.path.exists("token.txt"):
        with open("token.txt", "r") as f:
            token = f.read().strip()
        print(f"当前保存的token: {token[:20]}...")
        
        # 测试token是否有效
        test_url = "https://userapi.qiekj.com/user/info"
        headers = {
            "Authorization": token,
            "Version": "1.60.3",
            "channel": "android_app",
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; Redmi Note 11 Pro Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/100.0.4896.58 Mobile Safari/537.36"
        }
        try:
            response = requests.post(test_url, headers=headers, data={"token": token})
            if response.json().get("code") == 0:
                print("✅ 当前token有效")
            else:
                print("❌ 当前token已失效")
        except:
            print("⚠️  无法验证token状态")
    else:
        print("❌ 未找到保存的token文件")

if __name__ == "__main__":
    import os
    
    print("=" * 50)
    print("胖乖生活 Token 获取工具 (修复版)")
    print("=" * 50)
    
    # 显示当前状态
    debug_current_status()
    
    print("\n选择操作:")
    print("1. 获取新token")
    print("2. 手动输入token")
    print("3. 退出")
    
    choice = input("请输入选择 (1/2/3): ").strip()
    
    if choice == "1":
        phone = input("请输入手机号: ").strip()
        if len(phone) == 11 and phone.isdigit():
            get_token_fixed(phone)
        else:
            print("❌ 手机号格式错误")
    elif choice == "2":
        token = input("请输入token: ").strip()
        if token:
            with open("token.txt", "w") as f:
                f.write(token)
            print("✅ token已保存")
        else:
            print("❌ token不能为空")
    else:
        print("👋 退出程序")