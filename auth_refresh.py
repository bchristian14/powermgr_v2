# run nightly to check token expiry
# attempts refresh when < 15 days remaining.
# send notification on refresh success|failure

import json, logging, requests, smtplib, ssl
from config import *
from datetime import datetime as dt
from email.message import EmailMessage
from credentials import gmail_user, gmail_pwrd

logging.basicConfig(filename=LOG_FILE, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

msg = EmailMessage()
msg["From"] = gmail_user
msg["Subject"] = "Tesla Auth Token Refresh"
msg["To"] = ', '.join(NOTIFICATION_EMAILS)

def main():
    logger.debug("opening token file")
    with open(TESLA_TOKEN_FILE, "r") as f:
        token = json.loads(f.read())
    token_expiry = token["created_at"] + token["expires_in"]
    if token_expiry - dt.timestamp(dt.now()) < TOKEN_REFRESH_THRESHOLD:
        logger.info("attempting token refresh")
        refresh_payload = {"grant_type": "refresh_token",
                           "client_id": "ownerapi",
                           "refresh_token": token["refresh_token"],
                           }
        try:
            session = requests.Session()
            resp = session.post(TESLA_TOKEN_URL, headers={}, json=refresh_payload)
            new_token = json.loads(resp.text)
            #save to file
            with open(TESLA_TOKEN_FILE, "w") as f:
                f.write(json.dumps(new_token))
            new_token_expiry = dt.fromtimestamp(new_token["expires_in"] + new_token["created_at"])
            logger.info(f"Token Refreshed - expires {new_token_expiry.isoformat()}")
            msg.set_content(f"Success - new expiration {new_token_expiry.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            msg.set_content(f"Token Refresh FAILED! \n\n{e}")
        with smtplib.SMTP_SSL("smtp.gmail.com", EMAIL_PORT, context=ssl.create_default_context()) as gmail:
            gmail.login(gmail_user,gmail_pwrd)
            gmail.send_message(msg)


if __name__ == "__main__":
    main()
