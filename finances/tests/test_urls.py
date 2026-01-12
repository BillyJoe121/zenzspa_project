
from django.urls import reverse, resolve
from django.test import SimpleTestCase

class TestFinancesURLs(SimpleTestCase):
    def test_commission_ledger_list_url(self):
        url = reverse('commission-ledger-list')
        assert resolve(url).view_name == 'commission-ledger-list'

    def test_commission_ledger_status_url(self):
        url = reverse('commission-ledger-status')
        assert resolve(url).view_name == 'commission-ledger-status'

    def test_pse_banks_url(self):
        url = reverse('pse-banks')
        assert resolve(url).view_name == 'pse-banks'

    def test_initiate_appointment_payment_url(self):
        url = reverse('initiate-appointment-payment', args=['00000000-0000-0000-0000-000000000000'])
        assert resolve(url).view_name == 'initiate-appointment-payment'

    def test_initiate_vip_subscription_url(self):
        url = reverse('initiate-vip-subscription')
        assert resolve(url).view_name == 'initiate-vip-subscription'

    def test_wompi_webhook_url(self):
        url = reverse('wompi-webhook')
        assert resolve(url).view_name == 'wompi-webhook'

    def test_initiate_package_purchase_url(self):
        url = reverse('initiate-package-purchase')
        assert resolve(url).view_name == 'initiate-package-purchase'

    def test_create_pse_payment_url(self):
        url = reverse('create-pse-payment', args=['00000000-0000-0000-0000-000000000000'])
        assert resolve(url).view_name == 'create-pse-payment'

    def test_create_nequi_payment_url(self):
        url = reverse('create-nequi-payment', args=['00000000-0000-0000-0000-000000000000'])
        assert resolve(url).view_name == 'create-nequi-payment'

    def test_create_daviplata_payment_url(self):
        url = reverse('create-daviplata-payment', args=['00000000-0000-0000-0000-000000000000'])
        assert resolve(url).view_name == 'create-daviplata-payment'

    def test_create_bancolombia_transfer_payment_url(self):
        url = reverse('create-bancolombia-transfer-payment', args=['00000000-0000-0000-0000-000000000000'])
        assert resolve(url).view_name == 'create-bancolombia-transfer-payment'
