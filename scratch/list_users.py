from core.dynamodb_service import UsersTable
import json

users = UsersTable.scan()
for u in users:
    print(f"ID: {u.get('UserID')} | Email: {u.get('Email')} | Role: {u.get('Role')} | Active: {u.get('IsActive')}")
