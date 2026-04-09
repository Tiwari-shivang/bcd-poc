# Database Schema Documentation

## Tables Overview
- roles
- users
- leaves

---

## Table: roles

### Columns

- id (uuid, Primary Key, Default: uuid_generate_v4())
- name (varchar, Unique, Not Null)
- created_at (timestamp, Not Null, Default: current timestamp)
- updated_at (timestamp, Not Null, Default: current timestamp)

---

## Table: users

### Columns

- id (uuid, Primary Key, Default: uuid_generate_v4())
- first_name (varchar, Not Null)
- last_name (varchar, Not Null)
- email (varchar, Unique, Not Null)
- password (varchar, Not Null)
- role_id (uuid, Foreign Key → roles.id)
- created_at (timestamp, Not Null, Default: current timestamp)
- updated_at (timestamp, Not Null, Default: current timestamp)

### Relationships

- users.role_id → roles.id (Many-to-One)

---

## Table: leaves

### Columns

- id (uuid, Primary Key, Default: uuid_generate_v4())
- from_date (timestamp, Not Null)
- to_date (timestamp, Not Null)
- status (varchar, Not Null)
- reason (varchar, Not Null)
- user_id (uuid, Foreign Key → users.id)
- created_at (timestamp, Not Null, Default: current timestamp)
- updated_at (timestamp, Not Null, Default: current timestamp)

### Relationships

- leaves.user_id → users.id (Many-to-One)

---

## Relationships Summary

- users.role_id → roles.id
- leaves.user_id → users.id