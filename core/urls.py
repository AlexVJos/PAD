from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from django.contrib.auth import views as auth_views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'books', views.BookViewSet)
router.register(r'loans', views.LoanViewSet)
router.register(r'borrow', views.BorrowBookAPIView, basename='borrow')

urlpatterns = [
    # API URLs
    path('api/', include(router.urls)),

    # Template Views (Frontend)
    path('', views.HomeView.as_view(), name='home'),
    path('books/<int:pk>/', views.BookDetailView.as_view(), name='book_detail'),
    path('books/<int:pk>/borrow/', views.BorrowBookView.as_view(), name='borrow_book'),
    path('loans/<int:pk>/return/', views.ReturnBookView.as_view(), name='return_book'),
    path('my-loans/', views.MyLoansView.as_view(), name='my_loans'),

    # Auth URLs
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('register/', views.UserRegisterView.as_view(), name='register'),

    # Book Management
    path('books/add/', views.BookCreateView.as_view(), name='book_add'),
    path('books/<int:pk>/edit/', views.BookUpdateView.as_view(), name='book_edit'),
    path('books/<int:pk>/delete/', views.BookDeleteView.as_view(), name='book_delete'),
]