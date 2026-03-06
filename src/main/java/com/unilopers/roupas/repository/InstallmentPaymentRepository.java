package com.unilopers.roupas.repository;

import org.springframework.data.jpa.repository.JpaRepository;

import com.unilopers.roupas.domain.InstallmentPayment;

public interface InstallmentPaymentRepository extends JpaRepository<InstallmentPayment, String> {
    // Métodos customizados podem ser adicionados aqui
}
