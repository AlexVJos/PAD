from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, TemplateView

from .clients import (
    AnalyticsServiceClient,
    CatalogServiceClient,
    LoanServiceClient,
    NotificationServiceClient,
    ServiceClientError,
    UserServiceClient,
)
from .forms import BookForm, LoginForm, RegisterForm


User = get_user_model()


def _get_remote_user_id(request) -> int | None:
    return request.session.get("user_service_id")


def _normalize_loans(loans: list[dict]) -> list[dict]:
    for loan in loans:
        for field in ("loan_date", "due_date", "returned_date"):
            value = loan.get(field)
            if isinstance(value, str):
                try:
                    loan[field] = datetime.fromisoformat(value)
                except ValueError:
                    pass
    return loans


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        catalog_client = CatalogServiceClient()
        search = self.request.GET.get("q")
        try:
            books = catalog_client.list_books(search)
        except ServiceClientError as exc:
            messages.error(self.request, f"Не удалось загрузить книги: {exc}")
            books = []

        paginator = Paginator(books, 9)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "books": page_obj,
                "paginator": paginator,
                "page_obj": page_obj,
                "is_paginated": page_obj.has_other_pages(),
            }
        )

        try:
            context["metrics"] = AnalyticsServiceClient().summary()
        except ServiceClientError:
            context["metrics_error"] = True
        return context


class BookDetailView(LoginRequiredMixin, TemplateView):
    template_name = "core/book_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book_id = int(self.kwargs["pk"])
        catalog_client = CatalogServiceClient()
        loan_client = LoanServiceClient()
        try:
            book = catalog_client.get_book(book_id)
        except ServiceClientError as exc:
            messages.error(self.request, f"Книга недоступна: {exc}")
            book = None
        context["book"] = book
        user_id = _get_remote_user_id(self.request)
        has_loan = False
        if user_id:
            try:
                loans = loan_client.list_loans(user_id=user_id)
                has_loan = any(l["book_id"] == book_id and l["status"] == "active" for l in loans)
            except ServiceClientError as exc:
                messages.error(self.request, f"Не удалось загрузить займы: {exc}")
        context["user_has_active_loan"] = has_loan
        context["can_borrow"] = bool(book and book.get("available_copies", 0) > 0)
        return context


class BorrowBookView(LoginRequiredMixin, View):
    def post(self, request, pk):
        user_id = _get_remote_user_id(request)
        if not user_id:
            messages.error(request, "Не удалось определить пользователя сервиса.")
            return redirect("book_detail", pk=pk)
        loan_client = LoanServiceClient()
        catalog_client = CatalogServiceClient()
        try:
            loan_client.create_loan(user_id=user_id, user_name=request.user.username, book_id=pk)
        except ServiceClientError as exc:
            messages.error(request, f"Не удалось взять книгу: {exc}")
            return redirect("book_detail", pk=pk)

        try:
            book = catalog_client.get_book(pk)
            messages.success(request, f'Вы успешно взяли книгу "{book["title"]}".')
        except ServiceClientError:
            messages.success(request, "Вы успешно взяли книгу.")
        return redirect("book_detail", pk=pk)


class ReturnBookView(LoginRequiredMixin, View):
    def post(self, request, pk):
        user_id = _get_remote_user_id(request)
        if not user_id:
            messages.error(request, "Не удалось определить пользователя сервиса.")
            return redirect("my_loans")
        loan_client = LoanServiceClient()
        try:
            loan_client.return_loan(pk, user_id)
            messages.success(request, "Книга успешно возвращена.")
        except ServiceClientError as exc:
            messages.error(request, f"Не удалось вернуть книгу: {exc}")
        return redirect("my_loans")


class MyLoansView(LoginRequiredMixin, TemplateView):
    template_name = "core/my_loans.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        loan_client = LoanServiceClient()
        user_id = _get_remote_user_id(self.request)
        loans = []
        if user_id:
            try:
                loans = _normalize_loans(loan_client.list_loans(user_id=user_id))
            except ServiceClientError as exc:
                messages.error(self.request, f"Не удалось получить список займов: {exc}")
        paginator = Paginator(loans, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update(
            {
                "loans": page_obj,
                "paginator": paginator,
                "page_obj": page_obj,
                "is_paginated": page_obj.has_other_pages(),
                "now": timezone.now(),
            }
        )
        if user_id:
            try:
                context["notifications"] = NotificationServiceClient().list_notifications(user_id=user_id)
            except ServiceClientError:
                context["notifications"] = []
        else:
            context["notifications"] = []
        return context


class UserRegisterView(FormView):
    template_name = "registration/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        client = UserServiceClient()
        data = {
            "username": form.cleaned_data["username"],
            "email": form.cleaned_data["email"],
            "password": form.cleaned_data["password1"],
        }
        try:
            client.register(data)
            messages.success(self.request, "Регистрация успешна! Теперь вы можете войти.")
            return super().form_valid(form)
        except ServiceClientError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)


class UserLoginView(FormView):
    template_name = "registration/login.html"
    form_class = LoginForm

    def get_success_url(self):
        return self.request.GET.get("next") or reverse_lazy("home")

    def form_valid(self, form):
        client = UserServiceClient()
        try:
            token = client.login(form.cleaned_data["username"], form.cleaned_data["password"])
        except ServiceClientError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        user, _ = User.objects.get_or_create(
            username=token.username,
            defaults={"email": token.email},
        )
        user.email = token.email
        user.set_unusable_password()
        user.save()

        login(self.request, user)
        self.request.session["user_service_token"] = token.access_token
        self.request.session["user_service_id"] = token.user_id
        return super().form_valid(form)


class BookCreateView(LoginRequiredMixin, FormView):
    template_name = "core/book_form.html"
    form_class = BookForm
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        client = CatalogServiceClient()
        try:
            client.create_book(form.cleaned_data)
            messages.success(self.request, "Книга успешно добавлена.")
            return super().form_valid(form)
        except ServiceClientError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Добавить новую книгу"
        return context


class BookUpdateView(LoginRequiredMixin, FormView):
    template_name = "core/book_form.html"
    form_class = BookForm
    success_url = reverse_lazy("home")

    def dispatch(self, request, *args, **kwargs):
        try:
            self.book_data = CatalogServiceClient().get_book(self.kwargs["pk"])
        except ServiceClientError as exc:
            messages.error(request, f"Книга недоступна: {exc}")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            "title": self.book_data["title"],
            "author": self.book_data["author"],
            "isbn": self.book_data["isbn"],
            "total_copies": self.book_data["total_copies"],
            "available_copies": self.book_data["available_copies"],
        }

    def form_valid(self, form):
        client = CatalogServiceClient()
        try:
            client.update_book(self.kwargs["pk"], form.cleaned_data)
            messages.success(self.request, "Книга успешно обновлена.")
            return super().form_valid(form)
        except ServiceClientError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Редактировать книгу"
        return context


class BookDeleteView(LoginRequiredMixin, View):
    template_name = "core/book_confirm_delete.html"

    def get(self, request, pk):
        try:
            book = CatalogServiceClient().get_book(pk)
        except ServiceClientError as exc:
            messages.error(request, f"Книга недоступна: {exc}")
            return redirect("home")
        return render(request, self.template_name, {"book": book})

    def post(self, request, pk):
        client = CatalogServiceClient()
        try:
            client.delete_book(pk)
            messages.success(request, "Книга удалена.")
        except ServiceClientError as exc:
            messages.error(request, f"Удаление не удалось: {exc}")
        return redirect("home")