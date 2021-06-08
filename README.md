# powermgr_v2 - modifies powerwall battery schedule usings built-in python modules, and adjusts honeywell theromstats based on battery monitoring. Sends email notifications for events & errors using gmail.

### Requirements:
- python3 (tested with python 3.8 specifically)
- built-in modules: json, logging, smtplib, ssl, datetime, email.message
- other modules:  requests
- tesla account w/ powerwalls
- honeywell "total comfort control" account w/ compatible thermostats (only for thermostat functions contained in precool_check.py and thermostat_controller.py)


### initial setup:
1. clone this repo
2. manually create tesla.token file. steps to get the token are at https://tesla-api.timdorr.com/api-basics/authentication
3. create credentials.py as described below
4. update config.py as described below
5. test/validate functionality
6. create cron schedule; sample below
    

#### Included Files:
* ***README.md*** - this document
* ***auth_refresh.py*** - examines existing tesla auth token and will refresh the token if under under 15 days remain.
* ***config.py*** - contains variables to modify for the repo. for example, peak start/end times, API endpoints, notification emails, etc. - at minimum, this file must be updated with your notification emails, tesla energy site ID, and honeywell thermostat IDs
* ***eod_status.py*** - logs/emails current powerall remaining battery % and operating mode
* ***peak_manager.py*** - toggles powerwall mode between backup & self_consumption based on peak/offpeak times
* ***precool_check.py*** - checks remaining battery and sets thermostats to configured temperature if below threshold
* ***thermostat_controller.py*** - checks battery % and increase thermostats by 2 or 4 degress as battery thesholds are crossed.


#### Omitted files, but required for operation:
* ***battery.status*** - used by thermostat_controller to track which thresholds have been reached; should reset to 0 daily
* ***credentials.py*** - Stores credentials for email client & thermostat api
* ***tesla.token*** - stores current tesla token.


#### battery.status
* should just contain one of [012] depending on the most recent threshold crossed. Is reset to 0 daily by cronjob


#### credentials.py should contain the following variables with your credentials:
* gmail_user
* gmail_pwrd
* honeywell_user
* honeywell_pwrd


#### tesla.token is the json formatted access token, including the access token, token_type, expires_in, refresh_token, and created_at. Below is an example:
```{"access_token": "qts-0123456789thequickbrownfoxjumpedoverthelazydog012345678901234567", "token_type": "bearer", "expires_in": 3888000, "refresh_token": "01234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", "created_at": 1622683443}```


#### TODOs: 
- create initial setup script including:
    - create initial tesla auth token, getting credentials & captcha (if applicable) via interactive prompt
    - fetch & display or set the energy_site_id value
    - prompts for desired notification emails
    - fetch & display (or set) thermostat IDs


#### Sample crontab
```
# summer peaks
55 13 * 5-10 1-5 /usr/local/bin/python3.8 /path/to/powermgr/peak_manager.py
# summer off-peak
1 20 * 5-10 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/peak_manager.py
3 20 * 5-10 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/eod_status.py

#summer thermostat controller - run every 15 minutes from 14:00-19:45 weekdays from May to October
*/15 14-19 * 5-10 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/thermostat_controller.py

# winter peaks
55 4,16 * 1,2,3,4,11,12 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/peak_manager.py
# winter off-peaks
1 9,21 * 1,2,3,4,11,12 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/peak_manager.py
3 21 * 1,2,3,4,11,12 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/eod_status.py

#daily - reset battery.status, check/refresh tesla auth token, and run precool_check.py
1 0 * 5-10 1-5 echo -n '0' > /path/to/battery.status
0 12 * 5-10 1-5 /usr/local/bin/python3.8 /path/to/powermgr_v2/precool_check.py
30 21 * * * /usr/local/bin/python3.8 /path/to/powermgr_v2/auth_refresh.py
```


