# core/admin.py
from django.contrib import admin
from .models import Book, Loan

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'isbn', 'available_copies', 'total_copies')
    search_fields = ('title', 'author', 'isbn')
    list_filter = ('author',)
    ordering = ('title',)

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'loan_date', 'due_date', 'returned_date', 'is_returned')
    list_filter = ('is_returned', 'loan_date', 'due_date')
    search_fields = ('user__username', 'book__title', 'book__isbn')
    raw_id_fields = ('user', 'book') # Позволяет искать по ID вместо выпадающего списка
    actions = ['mark_loans_as_returned']

    def mark_loans_as_returned(self, request, queryset):
        # Отфильтровываем только те займы, которые еще не возвращены
        not_returned_loans = queryset.filter(is_returned=False)
        count = not_returned_loans.count()
        for loan in not_returned_loans:
            loan.mark_as_returned()
        self.message_user(request, f'{count} займ(ов) успешно отмечены как возвращенные.')
    mark_loans_as_returned.short_description = "Отметить выбранные займы как возвращенные"