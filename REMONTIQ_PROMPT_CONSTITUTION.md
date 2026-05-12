# 🏗️ Konstytucja Promptu RemontIQ

Poniżej znajduje się zaawansowany prompt, który definiuje architekturę i logikę biznesową systemu RemontIQ. Może on służyć jako baza do odtworzenia projektu lub instruowania modeli AI o sposobie działania aplikacji.

---

## 🎯 PROMPT: System Zarządzania Remontami "RemontIQ"

**Rola:** Działaj jako Senior Fullstack Architect & FinTech Expert.

**Cel:** Zaprojektuj i zaimplementuj fundamenty aplikacji SaaS "RemontIQ" do zarządzania procesami budowlanymi. Kluczowym elementem jest "Handshake 2.0" – system negocjacji cen między Inwestorem a Ekipą.

**Stack Technologiczny:**
- **Frontend:** Streamlit (Premium UI, dark mode, profesjonalny SaaS look).
- **Backend/DB:** Supabase (PostgreSQL) z silnym wykorzystaniem triggerów i constraintów.
- **Logika:** Python (Service-oriented architecture).

**Kluczowe Moduły do Zaimplementowania:**

1.  **Architektura SSoT (Single Source of Truth):**
    - Stwórz tabelę `tasks` z polem `state` (DRAFT, PRICED, APPROVED, IN_PROGRESS, BLOCKED, DONE, REJECTED).
    - Zaimplementuj maszynę stanów w PostgreSQL (Triggery), która pilnuje legalności przejść (np. nie można zakończyć zadania, które nie zostało zatwierdzone).

2.  **System Handshake 2.0 (Negocjacje):**
    - Mechanizm "zamkniętej pętli": Ekipa proponuje cenę -> Inwestor akceptuje lub daje kontrpropozycję -> Ekipa akceptuje lub negocjuje dalej.
    - Zmiana ceny o >20% w trakcie fazy `IN_PROGRESS` musi automatycznie ustawić stan `BLOCKED` i wymagać ponownego zatwierdzenia przez ekipę.

3.  **Silnik Planowania (Ordering Service):**
    - Obsługa zależności między zadaniami w dedykowanej tabeli relacyjnej `task_dependencies`.
    - Algorytm przeliczania osi czasu (Gantt) na podstawie `sort_order` i czasu trwania.

4.  **UI Role-Based:**
    - **Panel Inwestora:** Dashboard finansowy, akceptacja wycen, podgląd postępów.
    - **Panel Ekipy:** Zarządzanie kolejnością zadań, wysyłanie ofert cenowych, raportowanie zakończenia prac.

5.  **System Komunikacji i Audytu (Messenger & Activity Log):**
    - **Natywna Integracja:** Czat oparty na tabeli `task_comments`, a zdarzenia systemowe na `activity_log`.
    - **Model Iniekcji (Streamlit Cloud):** Ze względu na izolację sesji w folderze `pages/`, Czat musi być wstrzyknięty jako komponent (`components/chat_component.py`) bezpośrednio do `app.py`.
    - **Autoryzacja PIN-based:** Mapowanie ról logowania PIN (investor, crew) na stałe UUID (Inwestor: `...1`, Karol: `...2`) w celu zapewnienia spójności w bazie bez Supabase Auth.
    - **Bezpieczeństwo (RLS):** Dla tabel komunikacji RLS musi być wyłączony (DISABLE RLS), aby umożliwić zapisywanie wiadomości przez system logowania PIN.
    - **Otwarta Księga:** Interfejs wspiera widok globalny (cały projekt) oraz kontekstowy (konkretne zadanie).

**Wymagania Techniczne:**
- Kod musi być modularny (odseparowane serwisy: `TaskService`, `NegotiationService`, `OrderingService`).
- Użyj transakcji bazodanowych (`upsert` dla batchy), aby uniknąć niespójności przy zmianie kolejności.
- Każda zmiana stanu musi posiadać audyt (kto zmienił, kiedy i z jakiego powodu - `state_changed_reason`).

**Zadanie 1:** Wygeneruj schemat SQL bazy danych uwzględniający powyższe triggery i maszyny stanów.
**Zadanie 2:** Napisz szkielet `OrderingService` w Pythonie obsługujący nową tabelę zależności i system stanów `state`.

---

> [!TIP]
> Ten prompt kładzie nacisk na **bezpieczeństwo danych** i **logikę biznesową** zaszytą w bazie danych, co jest fundamentem stabilności RemontIQ.
