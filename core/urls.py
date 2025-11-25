from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("books/add/", views.BookCreateView.as_view(), name="book_add"),
    path("books/<int:pk>/", views.BookDetailView.as_view(), name="book_detail"),
    path("books/<int:pk>/borrow/", views.BorrowBookView.as_view(), name="borrow_book"),
    path("books/<int:pk>/edit/", views.BookUpdateView.as_view(), name="book_edit"),
    path("books/<int:pk>/delete/", views.BookDeleteView.as_view(), name="book_delete"),
    path("loans/<int:pk>/return/", views.ReturnBookView.as_view(), name="return_book"),
    path("my-loans/", views.MyLoansView.as_view(), name="my_loans"),
    path("login/", views.UserLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("register/", views.UserRegisterView.as_view(), name="register"),
]