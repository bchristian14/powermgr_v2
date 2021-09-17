from datetime import datetime as dt, timedelta
import json, logging, requests, smtplib, ssl
from email.message import EmailMessage
from credentials import gmail_user, gmail_pwrd
from config import *

logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


current = dt.now()
#current = dt.fromisoformat("2021-09-17T13:59:01")

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
        resp.raise_for_status()
        cur_reserve = resp.json()['response']['backup_reserve_percent']
        logger.info(f"Current Reserve Set: {cur_reserve}")
        season = "summer" if (
            SUMMER_FIRST_MONTH <= current.month <= SUMMER_LAST_MONTH
            ) else "winter"
        if current.strftime('%Y-%m-%d') in HOLIDAYS:
            logger.info("Today is a pricing holiday. No Action")
        elif is_peak(season):
            logger.info(f"Pricing: {season.upper()} ON-PEAK")
            if cur_reserve == 0:
                logger.info("Reserve already set to 0%.")
            else:
                set_reserve(session=tesla_session,
                            reserve_percent=float("0.0"),
                            header=tesla_headers)
        else:
            logger.info(f"Pricing: {season.upper()} OFF-PEAK")
            if cur_reserve == 100:
                logger.info("Reserve already set to 100%.")
            else:
                set_reserve(session=tesla_session,
                            reserve_percent=float("100.0"),
                            header=tesla_headers)
        logger.info("=====   END   =====")
    except Exception as error:
        logger.exception(error)
        msg.set_content(f"""\nError setting battery reserve. Manual update required!""")
        with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
            gmail.login(gmail_user,gmail_pwrd)
            gmail.send_message(msg)


def set_reserve(session, reserve_percent, header):
    logger.info(f"Changing reserve to {reserve_percent}%")
    payload = {"backup_reserve_percent": reserve_percent}
    set_resp = session.post(TESLA_RESERVE_URL,headers=header,json=payload)
    set_resp.raise_for_status()
    get_resp = session.get(TESLA_ENERGY_SITE_URL,headers=header)
    get_resp.raise_for_status()
    new_reserve = get_resp.json()['response']['backup_reserve_percent']
    logger.info(f"New Reserve = {new_reserve}%")


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
