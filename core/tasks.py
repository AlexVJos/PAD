# core/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from .models import Loan, User, Book
from django.template.loader import render_to_string
from django.utils.html import strip_tags

@shared_task
def send_loan_notification_email(loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
        user_email = loan.user.email
        book_title = loan.book.title

        subject = f"Уведомление о займе книги: {book_title}"
        html_message = render_to_string('emails/loan_notification.html', {
            'username': loan.user.username,
            'book_title': book_title,
            'loan_date': loan.loan_date,
            'due_date': loan.due_date,
        })
        plain_message = strip_tags(html_message)

        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL, # Используйте DEFAULT_FROM_EMAIL из settings.py
            [user_email],
            html_message=html_message,
            fail_silently=False,
        )
        print(f"Отправлено уведомление о займе для {user_email}")
    except Loan.DoesNotExist:
        print(f"Займ с ID {loan_id} не найден.")
    except Exception as e:
        print(f"Ошибка при отправке уведомления о займе: {e}")

@shared_task
def send_overdue_notification_email(loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
        user_email = loan.user.email
        book_title = loan.book.title

        subject = f"Срок возврата книги истек: {book_title}"
        html_message = render_to_string('emails/overdue_notification.html', {
            'username': loan.user.username,
            'book_title': book_title,
            'loan_date': loan.loan_date,
            'due_date': loan.due_date,
        })
        plain_message = strip_tags(html_message)

        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            html_message=html_message,
            fail_silently=False,
        )
        print(f"Отправлено уведомление о просрочке для {user_email}")
    except Loan.DoesNotExist:
        print(f"Займ с ID {loan_id} не найден.")
    except Exception as e:
        print(f"Ошибка при отправке уведомления о просрочке: {e}")

@shared_task
def check_overdue_loans_and_send_notifications():
    """
    Задача Celery, которая периодически проверяет просроченные займы
    и отправляет уведомления.
    """
    overdue_loans = Loan.objects.filter(
        due_date__lt=timezone.now(),
        is_returned=False
    )
    for loan in overdue_loans:
        print(f"Обнаружен просроченный займ: {loan.id}")
        send_overdue_notification_email.delay(loan.id)
    print("Проверка просроченных займов завершена.")