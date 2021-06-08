import json, logging, requests, smtplib, ssl
from credentials import honeywell_pwrd, honeywell_user, gmail_user, gmail_pwrd
from config import *
from email.message import EmailMessage



logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

msg = EmailMessage()
msg["From"] = gmail_user
msg["Subject"] = "Powerall Battery Alert"
msg["To"] = ', '.join(NOTIFICATION_EMAILS)


def get_setpoint(therm_session,device):
    THERMOSTAT_OPERATION_URL = f"{THERMOSTAT_BASE_URL}/Device/CheckDataSession/{device}"
    logger.debug(THERMOSTAT_OPERATION_URL)
    resp = therm_session.get(THERMOSTAT_OPERATION_URL)
    return resp.json()['latestData']['uiData']['CoolSetpoint']


def set_setpoint(therm_session,device,temp_change):
    data = {'SystemSwitch': None,
            'HeatSetpoint': None,
            'CoolSetpoint': int(get_setpoint(therm_session,device))+temp_change,
            'HeatNextPeriod': None,
            'CoolNextPeriod': 80,
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
        with open(BATTERY_STATUS_FILE) as f:
            battery_status=int(f.read())
    except Exception as e:
        logger.error(f"Thermostat Controller failed to get battery status: {e}")
    temp_increase = False
    if perc_charged <= FIRST_THRESHOLD and battery_status < 1:
        logger.info(f'Battery crossed 1st threshold, STATUS: {battery_status}, CHARGE: {perc_charged}%')
        temp_increase = 2
        new_state = 1
    if perc_charged <= SECOND_THRESHOLD and battery_status < 2:
        logger.info(f'Battery crossed 2nd threshold, STATUS: {battery_status}, CHARGE: {perc_charged}%')
        temp_increase = 2
        new_state = 2
    if perc_charged <= THIRD_THRESHOLD and battery_status < 3:
        logger.info(f'Battery crossed 3rd threshold, STATUS: {battery_status}, CHARGE: {perc_charged}%')
        temp_increase = 4
        new_state = 3
    if temp_increase:
        logger.info(f'Attempting to increasing setpoints by {temp_increase} degrees')
        msg.set_content(f"\n{perc_charged}% remaining\nAttempting to adjust thermostats by {temp_increase} degrees")
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
                set_setpoint(therm_session,device,temp_increase)
            with open(BATTERY_STATUS_FILE, 'w') as f:
                _ = f.write(str(new_state))
        except Exception as e:
            logger.error(f'Failed to adjust thermostats: {e}')


if __name__ == "__main__":
    main()
