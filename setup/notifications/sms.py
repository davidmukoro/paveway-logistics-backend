def send_notification_sms(*, phone, message):
    """
    Temporary SMS implementation.
    Replace with XWireless integration later.
    """

    print("=" * 70)
    print("SMS NOTIFICATION")
    print(f"TO      : {phone}")
    print(f"MESSAGE : {message}")
    print("=" * 70)

    return {
        "success": True,
        "phone": phone,
        "message": message,
    }
