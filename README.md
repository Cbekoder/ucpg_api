# Universal Crypto Payment Gateway (UCPG) API

A comprehensive backend API for anonymous cryptocurrency payment processing with one-time QR codes and provider integration.

## 🚀 Features

### Core Payment Features
- **Multi-currency Support**: Fiat (USD, EUR, UZS, KZT, etc.) and crypto (BTC, ETH, USDT, etc.)
- **Real-time Exchange Rates**: Integration with Binance and CoinGecko APIs
- **One-time QR Codes**: Secure promo links with automatic expiration
- **Anonymous Transactions**: Minimal data collection for maximum privacy
- **Commission Management**: Flexible commission rates per currency/provider

### Provider Integration
- **API-based Integration**: RESTful API for service providers
- **Webhook System**: Real-time transaction notifications
- **Provider Dashboard**: Transaction management and statistics
- **Custom Commission Rates**: Provider-specific pricing

### Admin Features
- **Comprehensive Dashboard**: Real-time statistics and monitoring
- **Transaction Management**: View, filter, and manage all transactions
- **Provider Management**: Add, configure, and monitor service providers
- **Commission Configuration**: Flexible rate management system
- **Export Functionality**: CSV/Excel export for reporting

### Security Features
- **Rate Limiting**: API endpoint protection
- **Request Logging**: Comprehensive audit trail
- **API Key Authentication**: Secure provider access
- **Security Headers**: OWASP-compliant security headers
- **Maintenance Mode**: Graceful service maintenance

## 📋 Requirements

- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Celery for background tasks

## 🛠️ Installation

### Using Docker (Recommended)

1. **Clone the repository**
```bash
git clone <repository-url>
cd ucpg_api
```

2. **Copy environment file**
```bash
cp env.example .env
```

3. **Update environment variables** in `.env` file

4. **Start services**
```bash
docker-compose up -d
```

5. **Run migrations and setup**
```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py setup_ucpg
docker-compose exec web python manage.py createsuperuser
```

### Manual Installation

1. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**
```bash
pip install -r requirements/develop.txt
```

3. **Setup database**
```bash
createdb ucpg_db
python manage.py migrate
python manage.py setup_ucpg
python manage.py createsuperuser
```

4. **Start Redis and Celery**
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery Worker
celery -A core worker -l info

# Terminal 3: Celery Beat
celery -A core beat -l info

# Terminal 4: Django
python manage.py runserver
```

## 🔧 Configuration

### Environment Variables

Key environment variables (see `env.example` for full list):

```env
# Database
DB_NAME=ucpg_db
DB_USER=postgres
DB_PASSWORD=postgres

# Redis
REDIS_URL=redis://localhost:6379/0

# UCPG Settings
DEFAULT_COMMISSION_RATE=0.05
PROMO_LINK_EXPIRY_HOURS=24

# Payment Gateways
STRIPE_SECRET_KEY=sk_test_...
COINGECKO_API_KEY=your_api_key
```

### Initial Setup

Run the setup command to create initial data:

```bash
python manage.py setup_ucpg
```

This creates:
- Supported currencies (USD, EUR, BTC, USDT, etc.)
- Default commission settings
- Sample provider for testing

## 📖 API Documentation

### Public Endpoints

#### Payment Creation
```http
POST /api/v1/payments/create/
Content-Type: application/json

{
  "amount": 100.00,
  "from_currency": "USD",
  "to_currency": "USDT",
  "contact_email": "user@example.com"
}
```

#### Transaction Status
```http
GET /api/v1/payments/{transaction_id}/status/
```

#### Promo Code Claiming
```http
POST /api/v1/promo/claim/
Content-Type: application/json

{
  "promo_code": "ABC123DEF456",
  "recipient_wallet": "0x1234...",
  "payout_method": "crypto"
}
```

#### Currency List
```http
GET /api/v1/currencies/
```

#### Exchange Rates
```http
GET /api/v1/exchange-rates/?from=USD&to=BTC
```

### Provider API Endpoints

#### Create Payment (Provider)
```http
POST /api/v1/providers/api/payment/
X-API-Key: ucpg_your_api_key_here
Content-Type: application/json

{
  "amount": 50.00,
  "currency": "USD",
  "service_data": {
    "plan": "premium",
    "duration": "monthly"
  },
  "customer_email": "customer@example.com"
}
```

#### Transaction Status (Provider)
```http
GET /api/v1/providers/api/transaction/{transaction_id}/status/
X-API-Key: ucpg_your_api_key_here
```

### Admin API Endpoints

All admin endpoints require authentication and admin privileges.

#### Dashboard Statistics
```http
GET /api/v1/admin/dashboard/
Authorization: Bearer your_jwt_token
```

#### Transaction Management
```http
GET /api/v1/admin/transactions/
Authorization: Bearer your_jwt_token
```

#### Provider Management
```http
GET /api/v1/admin/providers/
POST /api/v1/admin/providers/
Authorization: Bearer your_jwt_token
```

## 🔄 Background Tasks

The system uses Celery for background processing:

### Scheduled Tasks

- **Exchange Rate Updates**: Every 5 minutes
- **Transaction Expiry**: Every hour  
- **Webhook Delivery**: Every 5 minutes
- **Data Cleanup**: Daily
- **Report Generation**: Daily

### Manual Task Execution

```bash
# Update exchange rates
python manage.py shell -c "from apps.payments.tasks import update_exchange_rates; update_exchange_rates.delay()"

# Expire old transactions
python manage.py shell -c "from apps.payments.tasks import expire_old_transactions; expire_old_transactions.delay()"
```

## 🔒 Security

### API Security
- Rate limiting on all endpoints
- API key authentication for providers
- JWT authentication for admin endpoints
- Request logging and monitoring

### Data Security
- Minimal data collection (anonymous by design)
- Encrypted sensitive data storage
- Secure payment processing
- OWASP security headers

### Operational Security
- Maintenance mode support
- Health check endpoints
- Comprehensive error logging
- Audit trail for all actions

## 📊 Monitoring & Logging

### Health Checks
```http
GET /api/v1/health/
GET /api/v1/providers/health/
```

### Logging
- Request/response logging
- Error tracking
- Security event logging
- Performance monitoring

### Metrics
- Transaction volume and success rates
- Commission earnings
- Provider performance
- System resource usage

## 🧪 Testing

### Run Tests
```bash
python manage.py test
```

### API Testing
Use the included Swagger documentation at `/docs/` for interactive API testing.

### Provider Integration Testing
1. Create a test provider via admin panel
2. Use the generated API key for testing
3. Test webhook delivery with test endpoints

## 📦 Deployment

### Production Deployment

1. **Update settings**
```python
# core/settings/production.py
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com']
```

2. **Environment setup**
```bash
cp env.example .env
# Update production values
```

3. **Database migration**
```bash
python manage.py migrate --settings=core.settings.production
python manage.py collectstatic --settings=core.settings.production
```

4. **Process management**
```bash
# Use gunicorn for web server
gunicorn --bind 0.0.0.0:8000 core.wsgi:application

# Use supervisor for Celery
supervisorctl start celery-worker
supervisorctl start celery-beat
```

### Docker Production
```bash
docker-compose -f docker-compose.prod.yml up -d
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📝 License

This project is proprietary. All rights reserved.

## 🆘 Support

For technical support or integration help:
- Email: support@ucpg.com
- Documentation: `/docs/`
- Admin Panel: `/admin/`

## 🔄 Version History

### v1.0.0 (Current)
- Initial release
- Core payment processing
- Provider integration
- Admin dashboard
- Security features
- Docker support

---

**Note**: This is a production-ready backend system. Ensure proper security measures, monitoring, and backups are in place before deploying to production.
