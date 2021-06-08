from datetime import datetime as dt, timedelta
import json, logging, requests, smtplib, ssl
from email.message import EmailMessage
from credentials import gmail_user, gmail_pwrd
from config import *

logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


current = dt.now()

msg = EmailMessage()
msg["Subject"] = "Powerwall State Change Failure"
msg["To"] = ', '.join(NOTIFICATION_EMAILS)
msg['From'] = gmail_user


def main():
    try:
        logger.info("=====  BEGIN  =====")
        logger.debug("opening token file")
        with open(TESLA_TOKEN_FILE, "r") as f:
            token = json.loads(f.read())
        logger.debug("getting current mode")
        tesla_session = requests.Session()
        tesla_headers = {"Authorization": f"Bearer {token['access_token']}"}
        resp = tesla_session.get(TESLA_ENERGY_SITE_URL,headers=tesla_headers)
        cur_mode = resp.json()['response']['default_real_mode']
        logger.info(f"Current Mode: {cur_mode}")
        season = "summer" if (
            SUMMER_FIRST_MONTH <= current.month <= SUMMER_LAST_MONTH
            ) else "winter"
        if is_peak(season):
            logger.info(f"Pricing: {season.upper()} ON-PEAK")
            if cur_mode == "self_consumption":
                logger.info("Mode already set to self-consumption.")
            else:
                logger.info("Changing to self-consumption.")
                params = {"default_real_mode": "self_consumption"}
                resp = tesla_session.post(TESLA_OPERATIONS_URL,headers=tesla_headers,params=params)
                resp.raise_for_status()
                resp = tesla_session.get(TESLA_ENERGY_SITE_URL,headers=tesla_headers)
                new_mode = resp.json()['response']['default_real_mode']
                logger.info(f"New Mode: {new_mode}")
        else:
            logger.info(f"Pricing: {season.upper()} OFF-PEAK")
            if cur_mode == "backup":
                logger.info("Mode already set to backup.")
            else:
                logger.info("Changing to backup.")
                params = {"default_real_mode": "backup"}
                resp = tesla_session.post(TESLA_OPERATIONS_URL,headers=tesla_headers,params=params)
                resp.raise_for_status()
                resp = tesla_session.get(TESLA_ENERGY_SITE_URL,headers=tesla_headers)
                new_mode = resp.json()['response']['default_real_mode']
                logger.info(f"New Mode: {new_mode}")
        logger.info("=====   END   =====")
    except Exception as error:
        logger.exception(error)
        msg.set_content(f"""\nError setting battery mode. Manual update required!""")
        with smtplib.SMTP_SSL("smtp.gmail.com", port, context=ssl.create_default_context()) as gmail:
            gmail.login(guser,gpwd)
            gmail.send_message(msg)

def is_peak(season):
    if season == "winter": # is it winter
        morn_start = (dt.strptime(str(WINTER_MORNING_PEAK_START),"%H")
                      - timedelta(minutes=10)
                      ).time()
        morn_end = dt.strptime(str(WINTER_MORNING_PEAK_END),"%H").time()
        eve_start = (dt.strptime(str(WINTER_EVENING_PEAK_START), "%H")
                     - timedelta(minutes=10)
                     ).time()
        eve_end = dt.strptime(str(WINTER_EVENING_PEAK_END), "%H").time()
        # True if weekday between peak times
        return current.weekday() < 5 and \
               (morn_start < current.time() < morn_end or
                eve_start < current.time() < eve_end)
    else: # it is summer
        start = (dt.strptime(str(SUMMER_PEAK_START),"%H")
                 - timedelta(minutes=10)).time()
        end = dt.strptime(str(SUMMER_PEAK_END),"%H").time()
        # True if weekday between peak times
        return current.weekday() < 5 and (start < current.time() < end)

if __name__ == "__main__":
    main()
