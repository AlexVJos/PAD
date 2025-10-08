from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth.models import User

from .forms import UserCreationForm
from .models import Book, Loan
from .serializers import UserSerializer, BookSerializer, LoanSerializer, BorrowBookSerializer
from core.services import EmailNotificationService # Импортируем наш сервис уведомлений
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.views import View


# --- DRF API Views ---
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.all()
    serializer_class = LoanSerializer

    @action(detail=True, methods=['post'], name='Mark as Returned')
    def mark_returned(self, request, pk=None):
        loan = self.get_object()
        if not loan.is_returned:
            loan.mark_as_returned()
            return Response({'status': 'loan marked as returned'}, status=status.HTTP_200_OK)
        return Response({'status': 'loan already returned'}, status=status.HTTP_400_BAD_REQUEST)

class BorrowBookAPIView(viewsets.GenericViewSet):
    serializer_class = BorrowBookSerializer

    @action(detail=False, methods=['post'], name='Borrow Book')
    def borrow(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        loan = serializer.save()
        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)


# --- Django Template Views ---

class HomeView(LoginRequiredMixin, ListView):
    model = Book
    template_name = 'core/home.html'
    context_object_name = 'books'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(author__icontains=query) |
                Q(isbn__icontains=query)
            )
        return queryset


class BookDetailView(LoginRequiredMixin, DetailView):
    model = Book
    template_name = 'core/book_detail.html'
    context_object_name = 'book'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context['can_borrow'] = self.object.can_borrow()
            context['user_has_active_loan'] = Loan.objects.filter(
                user=self.request.user,
                book=self.object,
                is_returned=False
            ).exists()
        return context


class BorrowBookView(LoginRequiredMixin, View):
    def post(self, request, pk):
        book = get_object_or_404(Book, pk=pk)
        user = request.user

        try:
            existing_loan = Loan.objects.get(user=user, book=book)
        except Loan.DoesNotExist:
            existing_loan = None

        if not book.can_borrow():
            messages.error(request, 'Извините, все копии этой книги сейчас заняты.')
            return redirect('book_detail', pk=pk)

        if Loan.objects.filter(user=user, book=book, is_returned=False).exists():
            messages.warning(request, 'Вы уже взяли эту книгу и еще не вернули.')
            return redirect('book_detail', pk=pk)
        elif existing_loan:
            existing_loan.is_returned = False
            existing_loan.returned_date = None
            existing_loan.loan_date = timezone.now()
            existing_loan.due_date = timezone.now() + settings.LOAN_DUE_PERIOD
            existing_loan.save()
            messages.success(
                request,
                f'Вы успешно взяли книгу "{book.title}". '
                f'Срок возврата: {existing_loan.due_date.strftime("%Y-%m-%d")}.'
            )
            return redirect('book_detail', pk=pk)

        loan = Loan.objects.create(user=user, book=book, due_date=timezone.now() + settings.LOAN_DUE_PERIOD)
        EmailNotificationService.send_loan_confirmation(loan.id) # Отправка уведомления
        messages.success(request, f'Вы успешно взяли книгу "{book.title}". Срок возврата: {loan.due_date.strftime("%Y-%m-%d")}.')
        return redirect('book_detail', pk=pk)


class ReturnBookView(LoginRequiredMixin, View):
    def post(self, request, pk):
        loan = get_object_or_404(Loan, pk=pk, user=request.user, is_returned=False)
        loan.mark_as_returned()
        messages.success(request, f'Вы успешно вернули книгу "{loan.book.title}".')
        return redirect('my_loans')


class MyLoansView(LoginRequiredMixin, ListView):
    model = Loan
    template_name = 'core/my_loans.html'
    context_object_name = 'loans'
    paginate_by = 10

    def get_queryset(self):
        return Loan.objects.filter(user=self.request.user).order_by('-loan_date')


class UserRegisterView(CreateView):
    model = User
    form_class = UserCreationForm
    template_name = 'registration/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Регистрация успешна! Теперь вы можете войти.')
        return response

class BookCreateView(LoginRequiredMixin, CreateView):
    model = Book
    fields = ['title', 'author', 'isbn', 'total_copies', 'available_copies']
    template_name = 'core/book_form.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = "Добавить новую книгу"
        return context

class BookUpdateView(LoginRequiredMixin, UpdateView):
    model = Book
    fields = ['title', 'author', 'isbn', 'total_copies', 'available_copies']
    template_name = 'core/book_form.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = "Редактировать книгу"
        return context

class BookDeleteView(LoginRequiredMixin, DeleteView):
    model = Book
    template_name = 'core/book_confirm_delete.html'
    success_url = reverse_lazy('home')