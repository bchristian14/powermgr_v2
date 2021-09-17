import json, logging, requests, smtplib, ssl, time
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
        battery_power = resp.json()['response'][0]['battery_power']
        reserve_resp = tesla_session.get(TESLA_ENERGY_SITE_URL,headers=tesla_headers)
        reserve = reserve_resp.json()["response"]["backup_reserve_percent"]
        logger.info(f'EOD Charge: {perc_charged}')
        logger.info(f'EOD Reserve Setting: {reserve}')
        logger.info(f'EOD Discharge rate: {battery_power}')
        msg.set_content(f"""\nCharge: {perc_charged}%\nBattery Reserve Setting: {reserve}%\nDischarge rate: {battery_power}""")
        logger.debug(f"Email Message = {msg}")
    except Exception as error:
        logger.exception(error)
        msg.set_content(f"Exception getting EOD Status: {error}")
    with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
        gmail.login(gmail_user,gmail_pwrd)
        gmail.send_message(msg)
    try:
        if battery_power > 1500:
            logger.warn('Unexpected battery usage detected; rechecking in 5 minutes')
            time.sleep(300)
            resp = tesla_session.get(TESLA_PRODUCTS_URL,headers=tesla_headers)
            battery_check = resp.json()['response'][0]['battery_power']
            logger.info(f'Battery draw: {battery_check}')
            msg.set_content(f"5-minute follow-up - Battery Draw: {battery_check}")
            gmail.login(gmail_user,gmail_pwrd)
            gmail.send_message(msg)
    except Exception as error:
        logger.exception(error)
        msg.set_content(f"Exception re-setting to backup mode: {error}")


if __name__ == '__main__':
    main()
