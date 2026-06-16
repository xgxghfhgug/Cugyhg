# -*- coding: utf-8 -*-
import os
import asyncio
import re
import requests
from playwright.async_api import async_playwright

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MY_USER = os.getenv("MY_USER")
MY_PASS = os.getenv("MY_PASS")

TARGET_URL = "http://94.23.120.156/ints/client/SMSCDRStats"
LOGIN_URL = "http://94.23.120.156/ints/login"

sent_msgs = {}

# ===== UTILITIES =====
def extract_otp(msg):
    # ৪ থেকে ৮ ডিজিটের OTP বা হাইফেন দেওয়া OTP খুঁজে বের করবে
    match = re.search(r'\b(\d{4,8}|\d{3}-\d{3})\b', msg)
    return match.group(0) if match else "N/A"

def send_telegram(date_str, num, sms_text, otp, cli_source, is_update=False):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # নাম্বার মাস্কিং (উদাহরণ: +994XXXX0123)
    masked = num[:4] + "XXXX" + num[-4:] if len(num) > 8 else num
    
    header = " <b>UPDATED</b>" if is_update else ""
    
    # সুপার ক্লিন UI: শুধু ফ্ল্যাগ, সার্ভিস এবং মাস্কড নাম্বার
    text = f"{header}\n\n🚩 <b>{cli_source}</b> <code>{masked}</code>"

    # শুধুমাত্র OTP বাটন (Tap to Copy)
    keyboard = {
        "inline_keyboard": [
            [{"text": f" {otp}", "copy_text": {"text": otp}}]
        ]
    }

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except:
        return False

# ===== MAIN BOT =====
async def start_bot():
    print("🚀 Bot starting with Super Clean UI (Firebase Disabled)...")

    async with async_playwright() as p:
        # ব্রাউজার অপ্টিমাইজেশন
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        async def login():
            try:
                await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                await page.evaluate(f"""() => {{
                    const myUser = "{MY_USER}";
                    const myPass = "{MY_PASS}";
                    let userField, passField, ansField;

                    document.querySelectorAll('input').forEach(inp => {{
                        let p = (inp.placeholder || "").toLowerCase();
                        if (inp.type === 'password') passField = inp;
                        else if (p.includes('user') || inp.type === 'text') {{
                            if (!userField && !p.includes('answer')) userField = inp;
                        }}
                        if (p.includes('answer') || (inp.name || "").includes('ans')) ansField = inp;
                    }});

                    let match = document.body.innerText.match(/What is\\s+(\\d+)\\s*\\+\\s*(\\d+)/i);
                    let sum = match ? (parseInt(match[1]) + parseInt(match[2])) : "";

                    if (userField && passField && ansField && sum !== "") {{
                        userField.value = myUser;
                        passField.value = myPass;
                        ansField.value = sum;
                        userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        ansField.dispatchEvent(new Event('input', {{ bubbles: true }}));

                        for (let b of document.querySelectorAll('button, input[type="submit"]')) {{
                            if ((b.innerText || b.value || "").toLowerCase().includes('login')) {{
                                b.click();
                            }}
                        }}
                    }}
                }}""")
                await page.wait_for_timeout(3000)
                return True
            except:
                return False

        await login()
        is_first_scan = True

        while True:
            try:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                
                if "login" in page.url:
                    await login()
                    continue

                rows = await page.query_selector_all("table tbody tr")
                valid_rows = []

                for row in rows:
                    cols = await row.query_selector_all("td")
                    if len(cols) >= 7:
                        d = (await cols[0].inner_text()).strip()
                        n = (await cols[2].inner_text()).strip()
                        s = (await cols[4].inner_text()).strip()
                        cli = (await cols[3].inner_text()).strip()

                        if d and len(re.sub(r'\D', '', n)) >= 8:
                            valid_rows.append({"date": d, "num": n, "sms": s, "cli": cli})

                if valid_rows:
                    if is_first_scan:
                        # প্রথমবার রান হলে শুধু লেটেস্ট মেসেজটি নিবে
                        latest = valid_rows[0]
                        otp = extract_otp(latest['sms'])
                        send_telegram(latest['date'], latest['num'], latest['sms'], otp, latest['cli'])
                        sent_msgs[f"{latest['num']}|{latest['sms']}"] = latest['date']
                        is_first_scan = False
                    else:
                        # নতুন মেসেজ চেক করবে
                        for item in reversed(valid_rows):
                            uid = f"{item['num']}|{item['sms']}"
                            if uid not in sent_msgs:
                                otp = extract_otp(item['sms'])
                                if send_telegram(item['date'], item['num'], item['sms'], otp, item['cli']):
                                    sent_msgs[uid] = item['date']

                # মেমোরি ক্লিনআপ
                if len(sent_msgs) > 1000:
                    sent_msgs.clear()

            except Exception as e:
                print(f"Error encountered: {e}")
                await asyncio.sleep(5)

            await asyncio.sleep(2) # সার্ভার লোড কমাতে ২ সেকেন্ড গ্যাপ

if __name__ == "__main__":
    asyncio.run(start_bot())
    