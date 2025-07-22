from config import db

from datetime import datetime



class RestaurantMessage(db.Model):
    __tablename__ = 'restaurant'

    id = db.Column(db.Integer, primary_key=True)
    from_number = db.Column(db.Text, nullable=False)
    message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    bot_reply = db.Column(db.Text)
    status = db.Column(db.Text)
    reported = db.Column(db.Integer, default=0)


class Reservation(db.Model):
    __tablename__ = 'reservations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    contact_number = db.Column(db.Text, nullable=False)
    reservation_time = db.Column(db.DateTime(timezone=True), nullable=False)
    number_of_people = db.Column(db.Integer, nullable=False)
    table_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    reservations_done = db.Column(db.Boolean, default=False)
    rating = db.Column(db.Integer)


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    contact_number = db.Column(db.Text, nullable=False)
    order_details = db.Column(db.Text, nullable=False)
    delivery = db.Column(db.Text, default='No')
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    delivery_name = db.Column(db.Text)
    delivery_location = db.Column(db.Text)
    delivery_time = db.Column(db.Text)
    status = db.Column(db.Text)
    rating = db.Column(db.Integer)


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    contact_number = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False)


class AdminUser(db.Model):
    __tablename__ = 'admin_users'

    username = db.Column(db.String(255), primary_key=True)
    password_hash = db.Column(db.Text, nullable=False)


class MenuItem(db.Model):
    __tablename__ = 'menu'

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.Text, nullable=False)
    item_name = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(8, 2), nullable=False)
    available = db.Column(db.Boolean, default=True)
    highlight = db.Column(db.Boolean, default=False)
    image_url = db.Column(db.String(255), nullable=False)



class Rating(db.Model):
    __tablename__ = 'ratings'

    id = db.Column(db.Integer, primary_key=True)
    contact_number = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)
    rating = db.Column(db.SmallInteger, nullable=False)
    type = db.Column(db.Text)
    feedback = db.Column(db.Text)


class RestaurantTable(db.Model):
    __tablename__ = 'restaurant_tables'

    table_number = db.Column(db.Integer, primary_key=True)
    capacity = db.Column(db.Integer, nullable=False)
    is_available = db.Column(db.Boolean, default=True)


class UserMemory(db.Model):
    __tablename__ = 'user_memory'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contact_number = db.Column(db.Text, nullable=False)
    memory_key = db.Column(db.Text, nullable=False)
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('contact_number', 'memory_key', name='uq_contact_memory_key'),
    )

    def __repr__(self):
        return f"<UserMemory(contact_number={self.contact_number}, key={self.memory_key})>"