import json, logging, requests, smtplib, ssl
from credentials import honeywell_pwrd, honeywell_user, gmail_user, gmail_pwrd, openweather_key
from config import *
from email.message import EmailMessage



logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

msg = EmailMessage()
msg["From"] = gmail_user
msg["Subject"] = "Precool Notice"
msg["To"] = ', '.join(NOTIFICATION_EMAILS)

message_content = ''


def get_setpoint(therm_session,device):
    THERMOSTAT_OPERATION_URL = f"{THERMOSTAT_BASE_URL}/Device/CheckDataSession/{device}"
    logger.debug(THERMOSTAT_OPERATION_URL)
    resp = therm_session.get(THERMOSTAT_OPERATION_URL)
    return resp.json()['latestData']['uiData']['CoolSetpoint']


def set_setpoint(therm_session,device,new_temp):
    global message_content
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
        message_content += f"\nDevice: {device} set to {new_setpoint} degrees"
    except Exception as e:
        logger.error(f"Exception setting themostat {device}: {e}")
        message_content += f"\nException setting themostat {device}: {e}"


def main():
    global message_content
    logger.debug("opening token file")
    try:
        with open(TESLA_TOKEN_FILE, "r") as f:
            token = json.loads(f.read())
        logger.debug("getting Charge level")
        tesla_session = requests.Session()
        tesla_headers = {"Authorization": f"Bearer {token['access_token']}"}
        resp = tesla_session.get(TESLA_STATUS_URL,headers=tesla_headers)
        perc_charged = int(resp.json()['response']['percentage_charged'])
        logger.info(f'Current Charge: {perc_charged}')
    except Exception as e:
        logger.error(f"Precool Check failed to get battery status: {e}")
    openweather_url = f"https://api.openweathermap.org/data/2.5/onecall?lat={LAT}&lon={LON}&exclude=current,minutely,hourly,alerts&appid={openweather_key}&units=imperial"
    try:
        r = requests.get(openweather_url)
        forecast = r.json()["daily"][0]["temp"]["max"]
    except Exception as e:
        logger.errog(f'Failed to get weather data from: {r.url}')
    precool_reason = ''
    if forecast >= FORECAST_THRESHOLD:
        precool_reason += f"Forecasted high of {forecast} over {FORECAST_THRESHOLD}.\n"
    if perc_charged <= PRECOOL_THRESHOLD:
        precool_reason += f"Battery level of {perc_charged} below {PRECOOL_THRESHOLD}%.\n"
    if precool_reason:
        logger.info(f'{precool_reason}Attempting precool to {PRECOOL_TEMP} degrees')
        message_content += f"\n{precool_reason} Attempting precoool to {PRECOOL_TEMP} degrees."
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
        msg.set_content(message_content)
        with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
            gmail.login(gmail_user,gmail_pwrd)
            gmail.send_message(msg)


if __name__ == "__main__":
    main()
