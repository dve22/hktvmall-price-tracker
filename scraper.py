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
    print("正在啟動超強偽裝雲端瀏覽器...")
    with sync_playwright() as p:
        # 1. 啟用高級偽裝參數
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled', 
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--window-size=1920,1080'
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-HK",
            timezone_id="Asia/Hong_Kong"
        )
        
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        url = "https://www.hktvmall.com/hktv/zh/search_a?keyword=royal%20canin"
        print(f"正在模擬真人造訪網頁: {url}")
        
        page.goto(url, wait_until="commit", timeout=90000)
        
        print("網頁骨架已載入，正在等待 HKTVmall 動態商品列表渲染...")
        
        # 【核心修正】強迫瀏覽器至少要等到畫面上出現「任何一個商品簡介區塊」才繼續執行
        # HKTVmall 的商品組件通常帶有 class="product-brief" 或包含 data-algolia-object-id
        try:
            # 這裡設定最多等 15 秒讓商品跑出來
            page.wait_for_selector("[data-algolia-object-id], .product-brief, .product-list", timeout=15000)
            print("🎉 偵測到動態商品組件已成功渲染！")
        except Exception:
            print("⏱️ 等待商品組件超時，嘗試強制滾動以觸發非同步載入...")
            
        # 模擬真人隨機停頓與向下滾動，確保懶加載（Lazy Load）的商品圖片和價格全部出來
        for i in range(3):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i+1} / 3);")
            page.wait_for_timeout(2000)
        
        # 獲取最終渲染後的完整網頁原始碼
        html_content = page.content()
        browser.close()
        
    print("網頁數據下載完畢，開始進行數據提取...")
    
    today = datetime.now().strftime("%Y-%m-%d")
    products_list = []
    
    # 採用雙重正則表達式，確保新舊兩種 JSON 結構都能相容
    regex_list = [
        r'["\']code["\']\s*:\s*["\']([^"\']+)["\'].*?["\']name["\']\s*:\s*["\']([^"\']+)["\'].*?["\']value["\']\s*:\s*([\d.]+)',
        r'data-algolia-object-id="([^"]+)"[\s\S]*?class="brand-product-name">([^<]+)[\s\S]*?class="price">[\s\S]*?\$?\s*([\d,.]+)'
    ]
    
    seen_skus = set()
    
    for regex in regex_list:
        matches = re.findall(regex, html_content)
        for match in matches:
            sku = match[0].get_attribute() if hasattr(match[0], 'get_attribute') else match[0]
            sku = str(sku).strip()
            name = str(match[1]).strip()
            price = str(match[2]).strip().replace(",", "")
            
            if "royal" in name.lower() or "皇家" in name:
                if sku not in seen_skus:
                    seen_skus.add(sku)
                    try:
                        name = name.encode().decode('unicode_escape', errors='ignore')
                    except Exception:
                        pass
                    name = name.replace('\\"', '"').replace('\\/', '/')
                    product_url = f"https://www.hktvmall.com/hktv/zh/p/{sku}"
                    products_list.append([today, sku, name, price, product_url])
                    
    print(f"提取完畢！共成功捕捉到 {len(products_list)} 筆 Royal Canin 商品價格。")
    
    if len(products_list) > 0:
        filename = f"Royal_Canin_Prices_{today}.csv"
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["日期", "商品編號 (SKU)", "商品名稱", "價格 ($)", "商品連結"])
            writer.writerows(products_list)
            
        send_email(filename, today)
    else:
        print("====== 網頁內容調試片段 (前3000字) ======")
        print(html_content[:3000])
        print("=========================================")
        print("⚠️ 依然找不到數據。可能網頁轉為完全加密的 API 傳輸。")

def send_email(filename, date_string):
    sender_email = os.environ.get("SENDER_EMAIL")
    sender_password = os.environ.get("SENDER_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")
    
    if not sender_email or not sender_password:
        print("未設定 Email 憑證，跳過寄信。")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = f"【每週價格報告】HKTVmall ROYAL CANIN 自動更新 - {date_string}"
    
    body = "您好：\n\n附件為最新自動抓取的 HKTVmall ROYAL CANIN 價格歷史報告。"
    msg.attach(MIMEText(body, 'plain'))
    
    with open(filename, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {filename}")
        msg.attach(part)
        
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()
        print("Email 報告已成功寄出！")
    except Exception as e:
        print(f"郵件發送失敗: {e}")

if __name__ == "__main__":
    run()
