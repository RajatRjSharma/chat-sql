"""Unit tests for plural/singular NL noun matching."""

from __future__ import annotations

from app.services.nl_normalize import noun_surface_variants, nouns_match


class TestNounsMatch:
    def test_invoice_invoices(self) -> None:
        assert nouns_match("invoice", "invoices")
        assert nouns_match("invoices", "invoice")

    def test_sale_sales(self) -> None:
        assert nouns_match("sale", "sales")

    def test_customer_customers(self) -> None:
        assert nouns_match("customer", "customers")

    def test_company_companies(self) -> None:
        assert nouns_match("company", "companies")

    def test_class_classes(self) -> None:
        assert nouns_match("class", "classes")

    def test_unrelated(self) -> None:
        assert not nouns_match("order", "customer")
        assert not nouns_match("data", "database")


class TestVariants:
    def test_invoices_includes_invoice(self) -> None:
        assert "invoice" in noun_surface_variants("invoices")
        assert "invoices" in noun_surface_variants("invoice")
