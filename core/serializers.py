from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Book, Loan

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = '__all__'

class LoanSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    book = BookSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='user', write_only=True)
    book_id = serializers.PrimaryKeyRelatedField(queryset=Book.objects.all(), source='book', write_only=True)

    class Meta:
        model = Loan
        fields = '__all__'
        read_only_fields = ['loan_date', 'returned_date', 'is_returned']

class BorrowBookSerializer(serializers.Serializer):
    book_id = serializers.IntegerField()
    user_id = serializers.IntegerField()

    def validate(self, data):
        book_id = data.get('book_id')
        user_id = data.get('user_id')

        try:
            book = Book.objects.get(id=book_id)
        except Book.DoesNotExist:
            raise serializers.ValidationError({"book_id": "Книга не найдена."})

        if not book.can_borrow():
            raise serializers.ValidationError({"book_id": "Нет доступных копий этой книги."})

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError({"user_id": "Пользователь не найден."})

        if Loan.objects.filter(user=user, book=book, is_returned=False).exists():
            raise serializers.ValidationError({"non_field_errors": "Этот пользователь уже взял эту книгу."})

        data['book'] = book
        data['user'] = user
        return data

    def create(self, validated_data):
        book = validated_data['book']
        user = validated_data['user']
        loan = Loan.objects.create(user=user, book=book)
        from core.services import EmailNotificationService
        EmailNotificationService.send_loan_confirmation(loan.id)
        return loan