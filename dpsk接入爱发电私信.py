import requests
import time
import json
from datetime import datetime

# 配置参数
COOKIES = "请将此字段替换为你的登录Cookie"
MY_USER_ID = "请将此字段替换为你的爱发电账户ID"
DEEPSEEK_API_KEY = "请将此字段替换为你的deepseek API key"

# API配置
DIALOGS_URL = "https://afdian.com/api/message/dialogs?page=1&unread=1"
MESSAGES_URL_TEMPLATE = "https://afdian.com/api/message/messages?user_id={target_user_id}&type=old"
SEND_MESSAGE_URL = "https://afdian.com/api/message/send"
READ_URL_TEMPLATE = "https://afdian.com/api/message/messages?user_id={target_user_id}"

# DeepSeek其他配置
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
SYSTEM_PROMPT = "你是一位耐心的客服，回答的内容尽量简短"
AI_REPLY_SUFFIX = "\n\n[内容由AI生成，仅供参考]"

# 全局状态参数（需要重置的变量）
processed_user_ids = set()  # 已处理的用户ID
user_last_msg_id = {}  # 每个用户最后处理的消息ID
need_reset = False  # 重置标志


def reset_parameters():
    """重置所有状态参数"""
    global processed_user_ids, user_last_msg_id, need_reset
    print("\n----- 开始重置参数 -----")

    #  清空历史状态
    processed_user_ids = set()
    user_last_msg_id = {}
    need_reset = False

    #  重新初始化历史用户列表（类似刚启动时的状态）
    print("重新初始化历史用户列表...")
    initial_dialogs = get_dialogs()
    for dialog in initial_dialogs:
        processed_user_ids.add(dialog["user"]["user_id"])
    print(f"重置后已记录{len(processed_user_ids)}个历史用户")
    print("----- 参数重置完成 -----")


def get_dialogs():
    headers = {
        "Cookie": COOKIES,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(DIALOGS_URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("data", {}).get("list", []) if response.json().get("ec") == 200 else []
    except Exception as e:
        print(f"获取对话列表出错：{str(e)}")
        return []


def get_user_messages(target_user_id):
    url = MESSAGES_URL_TEMPLATE.format(target_user_id=target_user_id)
    headers = {"Cookie": COOKIES,
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get("data", {}).get("list", []) if response.json().get("ec") == 200 else []
    except Exception as e:
        print(f"获取用户[{target_user_id}]消息出错：{str(e)}")
        return []


def generate_ai_response(user_message):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message}],
        "temperature": 0.7
    }
    try:
        response = requests.post(DEEPSEEK_API_URL, json=data, headers=headers, timeout=15)
        response.raise_for_status()
        return f"{response.json()['choices'][0]['message']['content'].strip()}{AI_REPLY_SUFFIX}"
    except Exception as e:
        print(f"AI回复生成失败：{str(e)}")
        return None


def mark_user_messages_as_read(target_user_id):
    url = READ_URL_TEMPLATE.format(target_user_id=target_user_id)
    headers = {"Cookie": COOKIES,
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        if response.json().get("ec") == 200:
            print(f"用户[{target_user_id}]消息已标记为已读")
            return True
        else:
            print(f"用户[{target_user_id}]标记已读失败")
            return False
    except Exception as e:
        print(f"标记已读出错：{str(e)}")
        return False


def send_reply(target_user_id, content):
    global need_reset
    headers = {"Content-Type": "application/json", "Cookie": COOKIES,
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    data = {"user_id": target_user_id, "type": "1", "content": content}
    try:
        response = requests.post(SEND_MESSAGE_URL, json=data, headers=headers, timeout=10)
        result = response.json()
        if result.get("ec") == 200:
            print("回复发送成功")
            mark_user_messages_as_read(target_user_id)
            need_reset = True  # 回复成功后触发重置
            return True
        else:
            print(f"发送失败：{result.get('em', '未知错误')}")
            return False
    except Exception as e:
        print(f"发送回复失败：{str(e)}")
        return False


def process_new_user(target_user_id, user_name):
    print(f"\n检测到新增对话用户：{user_name}（ID：{target_user_id}）")
    messages = get_user_messages(target_user_id)
    if not messages:
        print(f"用户[{user_name}]暂无消息")
        return

    unprocessed = []
    last_msg_id = user_last_msg_id.get(target_user_id)
    for msg in messages:
        msg_info = msg["message"]
        if msg_info["sender"] != MY_USER_ID:
            content = msg_info["content"] if not isinstance(msg_info["content"],
                                                            dict) else f"订单消息：{msg_info['content'].get('out_trade_no', '未知订单')}"
            if msg_info["msg_id"] != last_msg_id:
                unprocessed.append({"id": msg_info["msg_id"], "content": content,
                                    "time": datetime.fromtimestamp(msg_info["send_time"]).strftime(
                                        "%Y-%m-%d %H:%M:%S")})
                user_last_msg_id[target_user_id] = msg_info["msg_id"]

    if not unprocessed:
        print(f"用户[{user_name}]暂无新消息")
        return

    latest = unprocessed[-1]
    print(f"最新消息[{latest['time']}]：{latest['content']}")
    reply = generate_ai_response(latest["content"])
    if reply:
        send_reply(target_user_id, reply)


def main(interval=7):
    global processed_user_ids, need_reset
    print("启动私信监控服务（每回复一条消息后重置参数）...")

    # 首次初始化历史用户
    print("初始化历史用户列表...")
    initial_dialogs = get_dialogs()
    for dialog in initial_dialogs:
        processed_user_ids.add(dialog["user"]["user_id"])
    print(f"初始已记录{len(processed_user_ids)}个历史用户，等待新增用户...")

    try:
        while True:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{current_time}] 监控中...")

            # 检查是否需要重置
            if need_reset:
                reset_parameters()  # 执行参数重置

            current_dialogs = get_dialogs()
            current_users = [{"id": d["user"]["user_id"], "name": d["user"]["name"]} for d in current_dialogs]
            new_users = [user for user in current_users if user["id"] not in processed_user_ids]

            for user in new_users:
                process_new_user(user["id"], user["name"])
                processed_user_ids.add(user["id"])
                if need_reset:  # 若已触发重置，退出当前循环
                    break

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n服务已手动停止")


if __name__ == "__main__":
    main()