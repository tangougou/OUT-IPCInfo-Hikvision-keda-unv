import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET
import json
import csv
from concurrent.futures import ThreadPoolExecutor

# ===========================================
# 配置区域
# ===========================================
HIK_USER = "admin"
HIK_PASS = "海康威视摄像机密码"

KEDACOM_USER = "admin"
KEDACOM_PASS = "科达摄像机密码"

UNIVIEW_USER = "admin"
UNIVIEW_PASS = "宇视摄像机密码"

# 扫描并发数
MAX_WORKERS = 20
# 单个设备响应超时时间（秒）
TIMEOUT = 5

# ===========================================
# 通用逻辑：判断设备类型
# ===========================================
def get_device_type(model):
    if not model:
        return "IPC"
    m = model.upper()
    # 常见的 NVR 特征字段
    nvr_keywords = ["NVR", "VMS", "DS-76", "DS-77", "DS-78", "DS-79", "DS-86", "DS-96", "NVR", "NSR"]
    for kw in nvr_keywords:
        if kw in m:
            return "NVR"
    return "IPC"

# ===========================================
# 海康设备识别（ISAPI）
# ===========================================
def get_hik_info(ip):
    url = f"http://{ip}/ISAPI/System/deviceInfo"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(HIK_USER, HIK_PASS), timeout=TIMEOUT)
        if r.status_code != 200:
            return None

        xml = ET.fromstring(r.text)
        # 兼容带命名空间的 XML
        def get_val(tag_name):
            for node in xml.iter():
                if node.tag.endswith(tag_name):
                    return node.text
            return ""

        model = get_val("model")
        return {
            "brand": "Hikvision",
            "ip": ip,
            "name": get_val("deviceName"),
            "model": model,
            "type": get_device_type(model)
        }
    except:
        return None

# ===========================================
# 科达设备识别（KDSAPI）
# ===========================================
def get_kedacom_info(ip):
    url = f"http://{ip}/kdsapi/system/deviceinfo"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(KEDACOM_USER, KEDACOM_PASS), timeout=TIMEOUT)
        if r.status_code != 200:
            return None

        xml = ET.fromstring(r.text)
        def get_val(tag_name):
            e = xml.find(tag_name)
            return e.text if e is not None else ""

        model = get_val("devicetype")
        return {
            "brand": "Kedacom",
            "ip": ip,
            "name": get_val("devicename"),
            "model": model,
            "type": get_device_type(model)
        }
    except:
        return None

# ===========================================
# 宇视设备识别（LAPI）
# ===========================================
def get_uniview_info(ip):
    url = f"http://{ip}/LAPI/V1.0/Channel/0/System/DeviceBasicInfo"
    try:
        r = requests.get(url, auth=HTTPDigestAuth(UNIVIEW_USER, UNIVIEW_PASS), timeout=TIMEOUT)
        if r.status_code != 200:
            return None

        data = r.json()
        d = data.get("Response", {}).get("Data", {})
        if not d:
            return None

        model = d.get("DeviceModel", "")
        return {
            "brand": "Uniview",
            "ip": ip,
            "name": model, # 宇视基本信息通常型号即名称
            "model": model,
            "type": get_device_type(model)
        }
    except:
        return None

# ===========================================
# 自动识别入口
# ===========================================
def detect_device(ip):
    # 按照 海康 -> 科达 -> 宇视 顺序尝试
    methods = [get_hik_info, get_kedacom_info, get_uniview_info]
    for method in methods:
        info = method(ip)
        if info:
            print(f" [√] {ip} 识别成功: {info['brand']} - {info['model']}")
            return info
    print(f" [×] {ip} 识别失败")
    return {"ip": ip, "status": "failed"}

# ===========================================
# 主程序
# ===========================================
def main():
    cameras = []
    nvrs = []
    failed = []

    # 1. 读取 IP
    try:
        with open("iplist.txt", "r", encoding="utf-8") as f:
            ips = [i.strip() for i in f if i.strip()]
    except FileNotFoundError:
        print("错误: 未找到 iplist.txt 文件")
        return

    print(f"开始扫描，共计 {len(ips)} 个 IP，线程数: {MAX_WORKERS}...")

    # 2. 多线程扫描
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(detect_device, ips))

    # 3. 结果归类
    for info in results:
        if "brand" not in info:
            failed.append(info)
        elif info["type"] == "NVR":
            nvrs.append(info)
        else:
            cameras.append(info)

    # 4. 保存结果
    def save_csv(filename, rows, headers):
        with open(filename, "w", newline="", encoding="utf-8-sig") as f: # utf-8-sig 解决 Excel 中文乱码
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            for r in rows:
                # 过滤掉不属于 headers 的 key
                filtered_row = {k: v for k, v in r.items() if k in headers}
                w.writerow(filtered_row)

    main_headers = ["ip", "brand", "name", "model", "type"]
    save_csv("camera.csv", cameras, main_headers)
    save_csv("nvr.csv", nvrs, main_headers)
    save_csv("failed.csv", failed, ["ip"])

    print("\n" + "="*30)
    print(f"扫描结束：")
    print(f"  摄像头：{len(cameras)} 台 (详见 camera.csv)")
    print(f"  NVR/主机：{len(nvrs)} 台 (详见 nvr.csv)")
    print(f"  识别失败：{len(failed)} 个 (详见 failed.csv)")
    print("="*30)

if __name__ == "__main__":
    main()