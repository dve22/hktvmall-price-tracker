import os
import re
import csv
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from playwright.sync_api import sync_playwright

def run():
    print("正在啟動雲端瀏覽器...")
    with sync_playwright() as p:
        # 啟動無頭瀏覽器，並設定模擬真人瀏覽器的參數
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-HK"
        )
        page = context.new_page()
        
        # 前往 HKTVmall 搜尋頁面
        url = "https://www.hktvmall.com/hktv/zh/search_a?keyword=royal%20canin"
        print(f"正在前往網頁: {url}")
        
        # 等待網頁載入，並給予最多 60 秒時間
        page.goto(url, wait_until="networkidle", timeout=60000)
        
        # 模擬向下滾動網頁，確保動態加載的商品全部跑出來
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        page.wait_for_timeout(3000) # 等待 3 秒
        
        # 獲取渲染完成後的完整網頁原始碼
        html_content = page.content()
        browser.close()
        
    print("網頁載入完成，開始使用『暴力特徵法』掃描數據...")
    
    today = datetime.now().strftime("%Y-%m-%d")
    products_list = []
    
    # 這是最暴力的結構掃描，直接在原始碼撈取符合的產品區塊
    block_regex = r'\{"code":"([^"]+)"[^}]+?"name":"([^"]+)"[^}]+?"value":([\d.]+)'
    matches = re.findall(block_regex, html_content)
    
    seen_skus = set()
    for match in matches:
        sku = match[0]
        name = match[1]
        price = match[2]
        
        # 過濾雜訊，確保是 Royal Canin 相關產品
        if "royal" in name.lower() or "皇家" in name:
            if sku not in seen_skus:
                seen_skus.add(sku)
                # 解碼 Unicode 萬國碼
                name = name.encode().decode('unicode_escape', errors='ignore').replace('\\"', '"')
                product_url = f"https://www.hktvmall.com/hktv/zh/p/{sku}"
                products_list.append([today, sku, name, price, product_url])
                
    print(f"掃描結束，共找到 {len(products_list)} 筆商品。")
    
    if len(products_list) > 0:
        filename = f"Royal_Canin_Prices_{today}.csv"
        # 寫入 CSV，使用 utf-8-sig 確保 Excel 打開中文不亂碼
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["日期", "商品編號 (SKU)", "商品名稱", "價格 ($)", "商品連結"])
            writer.writerows(products_list)
            
        # 寄送 Email
        send_email(filename, today)
    else:
        print("警告：未抓取到任何商品數據，可能網頁結構發生重大改變。")

def send_email(filename, date_string):
    # 從 GitHub Secrets 安全讀取郵箱設定
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD") # 這裡要填 Gmail 的「應用程式密碼」
    receiver_email = os.environ.get("RECEIVER_EMAIL")
    
    if not sender_email or not sender_password:
        print("未設定 Email 環境變數，跳過寄信步驟。CSV 已保存在雲端。")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"【每週價格報告】HKTVmall ROYAL CANIN 自動更新 - {date_string}"
    
    body = "您好：\n\n附件為本週一最新自動抓取的 HKTVmall ROYAL CANIN 價格報告報告。"
    msg.attach(MIMEText(body, 'plain'))
    
    # 讀取 CSV 檔案並作為附件
    with open(filename, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {filename}")
        msg.attach(part)
        
    try:
        server = smtplib.SMTP('smtp.gmail.com', 547) # 使用安全端口
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("Email 報告已成功寄出！")
    except Exception as e:
        # 如果 547 失敗，嘗試標準 587 端口
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
            server.quit()
            print("Email 報告已透過備用端口成功寄出！")
        except Exception as err:
            print(f"郵件發送失敗: {err}")

if __name__ == "__main__":
    run()
