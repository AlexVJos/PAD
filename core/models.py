# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class Book(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название")
    author = models.CharField(max_length=200, verbose_name="Автор")
    isbn = models.CharField(max_length=13, unique=True, verbose_name="ISBN")
    available_copies = models.IntegerField(default=1, verbose_name="Доступные копии")
    total_copies = models.IntegerField(default=1, verbose_name="Всего копий")

    class Meta:
        verbose_name = "Книга"
        verbose_name_plural = "Книги"

    def __str__(self):
        return f"{self.title} by {self.author}"

    def can_borrow(self):
        return self.available_copies > 0

class Loan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='loans', verbose_name="Пользователь")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='loans', verbose_name="Книга")
    loan_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата выдачи")
    due_date = models.DateTimeField(verbose_name="Дата возврата")
    returned_date = models.DateTimeField(null=True, blank=True, verbose_name="Дата возврата фактически")
    is_returned = models.BooleanField(default=False, verbose_name="Возвращена")

    class Meta:
        verbose_name = "Займ"
        verbose_name_plural = "Займы"
        # Запрещаем одному пользователю брать одну и ту же книгу несколько раз, пока она не возвращена
        unique_together = ('user', 'book', 'is_returned')
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'book'],
                condition=models.Q(is_returned=False),
                name='unique_active_loan'
            )
        ]


    def __str__(self):
        return f"{self.user.username} borrowed {self.book.title}"

    def save(self, *args, **kwargs):
        if not self.id:  # При создании новой записи займа
            if not self.due_date:
                # Устанавливаем срок возврата, например, через 14 дней
                self.due_date = timezone.now() + timedelta(days=14)
            # Уменьшаем количество доступных копий
            self.book.available_copies -= 1
            self.book.save()
        super().save(*args, **kwargs)

    def mark_as_returned(self):
        self.returned_date = timezone.now()
        self.is_returned = True
        self.book.available_copies += 1
        self.book.save()
        self.save()