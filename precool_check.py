import json, logging, requests, smtplib, ssl
from credentials import honeywell_pwrd, honeywell_user, gmail_user, gmail_pwrd
from config import *
from email.message import EmailMessage



logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

msg = EmailMessage()
msg["From"] = gmail_user
msg["Subject"] = "Precool Notice"
msg["To"] = ', '.join(NOTIFICATION_EMAILS)


def get_setpoint(therm_session,device):
    THERMOSTAT_OPERATION_URL = f"{THERMOSTAT_BASE_URL}/Device/CheckDataSession/{device}"
    logger.debug(THERMOSTAT_OPERATION_URL)
    resp = therm_session.get(THERMOSTAT_OPERATION_URL)
    return resp.json()['latestData']['uiData']['CoolSetpoint']


def set_setpoint(therm_session,device,new_temp):
    data = {'SystemSwitch': None,
            'HeatSetpoint': None,
            'CoolSetpoint': new_temp,
            'HeatNextPeriod': None,
            'CoolNextPeriod': 56,
            'StatusHeat': None,
            'StatusCool': 1,
            'DeviceID': device,
        }
    logger.debug(data)
    try:
        resp = therm_session.post(THERMOSTAT_OPERATION_URL, data=data)
        resp.raise_for_status()
        logger.debug(resp.json())
        new_setpoint = get_setpoint(therm_session,device)
        logger.info(f"Device: {device} set to {new_setpoint} degrees")
        msg.set_content(f"Device: {device} set to {new_setpoint} degrees")
    except Exception as e:
        logger.error(f"Exception setting themostat {device}: {e}")
        msg.set_content(f"Exception setting themostat {device}: {e}")
    with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
        gmail.login(gmail_user,gmail_pwrd)
        gmail.send_message(msg)


def main():
    logger.debug("opening token file")
    try:
        with open(TESLA_TOKEN_FILE, "r") as f:
            token = json.loads(f.read())
        logger.debug("getting Charge level")
        tesla_session = requests.Session()
        tesla_headers = {"Authorization": f"Bearer {token['access_token']}"}
        resp = tesla_session.get(TESLA_PRODUCTS_URL,headers=tesla_headers)
        perc_charged = int(resp.json()['response'][0]['percentage_charged'])
        logger.info(f'Current Charge: {perc_charged}')
    except Exception as e:
        logger.error(f"Precool Check failed to get battery status: {e}")
    if perc_charged <= PRECOOL_THRESHOLD:
        logger.info(f'Attempting precool - setting thermostats to {PRECOOL_TEMP} degrees')
        msg.set_content(f"\n{perc_charged}% below threshold of {PRECOOL_THRESHOLD}; precoooling to {PRECOOL_TEMP} degrees")
        with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
            gmail.login(gmail_user,gmail_pwrd)
            gmail.send_message(msg)
        params = {'UserName': honeywell_user,
                  'Password': honeywell_pwrd,
                  'RememberMe': 'false',
                  'timeOffset': 0
                  }
        try:
            therm_session = requests.Session()
            therm_session.headers['X-Requested-With'] = 'XMLHttpRequest'
            therm_session.get(THERMOSTAT_BASE_URL, timeout=60)
            login = therm_session.post(THERMOSTAT_BASE_URL,params=params,timeout=60)
            login.json()
            for device in THERMOSTAT_IDS:
                set_setpoint(therm_session,device,PRECOOL_TEMP)
        except Exception as e:
            logger.error(f'Failed to adjust thermostats: {e}')


if __name__ == "__main__":
    main()


