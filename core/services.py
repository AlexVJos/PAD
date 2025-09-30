# core/services.py
from .tasks import send_loan_notification_email, send_overdue_notification_email

class EmailNotificationService:
    @staticmethod
    def send_loan_confirmation(loan_id):
        send_loan_notification_email.delay(loan_id)

    @staticmethod
    def send_overdue_alert(loan_id):
        send_overdue_notification_email.delay(loan_id)