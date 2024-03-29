# single stop for variables throughout deployment

# global variables - log file & email variables
LOG_FILE = '/root/powermgr.log'
NOTIFICATION_EMAILS = ["email@example.com","email2@example.com"] #list of emails to send to 
EMAIL_PORT = 465

# thermostat_controller.py - increase a/c coolpoint when remaining battery percentage crosses thresholds
THERMOSTAT_IDS = [123456,123457] #list of thermostat IDs
THERMOSTAT_BASE_URL = 'https://www.mytotalconnectcomfort.com/portal'
THERMOSTAT_OPERATION_URL = f"{THERMOSTAT_BASE_URL}/Device/SubmitControlScreenChanges"
FIRST_THRESHOLD = 50
SECOND_THRESHOLD = 35
THIRD_THRESHOLD = 20
BATTERY_STATUS_FILE = '/root/battery.status'

# pre_cool.py - set thermostats to PRECOOL_TEMP if battery percent below PRECOOL_THRESHOLD
PRECOOL_TEMP = 67
PRECOOL_THRESHOLD = 90
LAT = 40.71  # set to your local latitude for weather forecast 
LON = -74.00 # set to your local longitute for weather forecast 
FORECAST_THRESHOLD = 105

# peak_manager.py - set powerwall mode to self_consumption during peak, and backup during off-peak
SUMMER_FIRST_MONTH = 5
SUMMER_LAST_MONTH = 10
SUMMER_PEAK_START = 14
SUMMER_PEAK_END = 20
WINTER_MORNING_PEAK_START = 5
WINTER_MORNING_PEAK_END = 9
WINTER_EVENING_PEAK_START = 17
WINTER_EVENING_PEAK_END = 21
# holidays on which utility observes off-peak pricing
NEW_YEARS = '2021-01-01'
MEMORIAL_DAY = '2021-05-31'
INDEPENDENCE_DAY = '2021-07-05'
LABOR_DAY = '2021-09-06'
THANKSGIVING = '2021-11-25'
CHRISTMAS = '2021-12-24'
HOLIDAYS = (NEW_YEARS, MEMORIAL_DAY, INDEPENDENCE_DAY, LABOR_DAY, THANKSGIVING, CHRISTMAS)



# Tesla Auth & API variables
TOKEN_REFRESH_THRESHOLD = 15*24*60*60
TESLA_ENERGY_SITE_ID = 123456789012 # replace with your energy site ID
TESLA_TOKEN_URL = "https://owner-api.teslamotors.com/oauth/token"
TESLA_AUTH_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TESLA_CALLBACK = "https://auth.tesla.com/void/callback"
TESLA_API_URL = "https://owner-api.teslamotors.com/api/1"
TESLA_TOKEN_FILE = "/root/tesla.token"
TESLA_ENERGY_SITE_URL = f"{TESLA_API_URL}/energy_sites/{TESLA_ENERGY_SITE_ID}/site_info"
TESLA_RESERVE_URL = f"{TESLA_API_URL}/energy_sites/{TESLA_ENERGY_SITE_ID}/backup"
TESLA_STATUS_URL = f"{TESLA_API_URL}/energy_sites/{TESLA_ENERGY_SITE_ID}/live_status"
