import json, logging, requests, smtplib, ssl
from email.message import EmailMessage
from config import *
from credentials import gmail_user,gmail_pwrd

logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


msg = EmailMessage()
msg["Subject"] = "Powerwall EOD Status"
msg["To"] = ', '.join(NOTIFICATION_EMAILS)
msg['From'] = gmail_user


def main():
    try:
        with open(TESLA_TOKEN_FILE, "r") as f:
            token = json.loads(f.read())
        logger.debug("EOD - getting Charge level")
        tesla_session = requests.Session()
        tesla_headers = {"Authorization": f"Bearer {token['access_token']}"}
        resp = tesla_session.get(TESLA_PRODUCTS_URL,headers=tesla_headers)
        perc_charged = int(resp.json()['response'][0]['percentage_charged'])
        mode_resp = tesla_session.get(TESLA_ENERGY_SITE_URL,headers=tesla_headers)
        mode = mode_resp.json()["response"]["default_real_mode"]
        logger.info(f'End of Day Charge: {perc_charged}')
        logger.info(f'End of Day Status: {mode}')
        msg.set_content(f"""\nBattery remaining: {perc_charged}\nCurrent Mode: {mode}""")
        logger.debug(f"Email Message = {msg}")
    except Exception as error:
        logger.exception(error)
        msg.set_content(f"Exception getting EOD Status: {error}")
    with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
        gmail.login(gmail_user,gmail_pwrd)
        gmail.send_message(msg)



if __name__ == '__main__':
    main()
