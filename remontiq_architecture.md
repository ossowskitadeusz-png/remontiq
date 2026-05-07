# Architektura i Logika Aplikacji RemontIQ (Wersja v2.0 po Sprincie 2)

Niniejszy dokument przedstawia pełną logiczną strukturę, schemat bazy danych oraz przepływ informacji po wdrożeniu logiki synchronizacji i zarządzania kosztami. Służy on do dalszej analizy i wyłapywania luk logicznych.

---

## 1. Założenia Systemu i Role
RemontIQ to inteligentny asystent wykończenia wnętrz, który odpowiada na pytanie: *"Co muszę zrobić teraz, aby remont nie stanął?"*.

*   **Widok Inwestora:** Pełen dostęp do zarządzania budżetem, materiałami, problemami i harmonogramem.
*   **Widok Ekipy Budowlanej:** Ograniczony interfejs skupiony wyłącznie na zgłaszaniu zapotrzebowań (brakujące materiały) i weryfikacji dostępnych na miejscu towarów. Całkowity brak dostępu do cen i budżetu.

---

## 2. Złota Zasada: Źródła Prawdy (Single Source of Truth)
W wersji 2.0 system ściśle rozdziela, skąd pochodzi dana informacja, aby zapobiec rozjazdowi danych (tzw. "chrupaniu"):

1.  **Stan logistyczny materiału (Co mam, gdzie to jest):** Tabela `materials`.
2.  **Koszty materiału (Ile to naprawdę kosztowało):** Suma kolumny `amount` z tabeli `expenses` dla danego materiału (wyliczane przez Sync Engine). Nigdy nie edytowane ręcznie!
3.  **Ilość dotarczona na budowę:** Suma kolumny `quantity` z tabeli `expenses` powiązanych z danym materiałem (wyliczane przez Sync Engine).
4.  **Dostępność dla ekipy:** Flaga `materials.available_for_crew`.
5.  **Historia pieniędzy:** Tabela `expenses`. To jedyne miejsce dodawania i kasowania operacji finansowych.
6.  **Pilność i Alerty:** Wyliczane "w locie" przez funkcję Scoringową na Dashboardzie. Dashboard nie przechowuje swoich danych.

---

## 3. Schemat Bazy Danych (Encje)

System działa na lokalnej bazie SQLite. Wszystkie główne tabele posiadają flagę `is_deleted` dla tzw. "miękkiego usuwania" (Archiwizacji).

1. **`settings`** (Konfiguracja globalna m.in. flaga `startup_wizard_completed`).
2. **`rooms`** (`name` UNIQUE, `budget`).
3. **`materials`** *(Serce logistyki)*
   - `name`, `status`, `location`, `notes` (notatki inwestora).
   - `quantity_planned`, `quantity_received` (Zasilane automatycznie przez Sync Engine), `unit` (szt, m2, l, kg).
   - `available_for_crew` (Boolean: ekipa może tego użyć).
   - `crew_confirmed` (Boolean: ekipa sprawdziła, że zgadza się jakość/wymiary).
   - `needed_by`, `lead_time_days` (Czas na wyliczenie daty zamówienia).
   - `cost_actual` (Suma wydatków. Nadpisywane tylko przez Sync Engine).
   - `is_deleted`
4. **`expenses`** *(Historia pieniędzy)*
   - `description`, `amount` (Kwota), `quantity` (Ilość nabyta podczas tego wydatku), `date`.
   - `material_id` (Opcjonalny klucz obcy do `materials`).
   - `is_deleted`
5. **`crew_requests`** *(Wymogi od ekipy)*
   - `title`, `needed_by`, `status`, `is_blocker`, `is_deleted`.
6. **`tasks`** *(Zadania i harmonogram)*
   - `name`, `status`, `priority`, `planned_start`, `assignee`, `progress`, `is_deleted`.
7. **`decisions`** *(Decyzje projektowe)*
   - `title`, `due_date`, `status`, `impact`, `is_deleted`.
8. **`issues`** *(Ryzyka)*
   - `title`, `status`, `is_deleted`.

---

## 4. Sync Engine (Logika Synchronizacji Wydatki ↔ Materiały)

Aplikacja posiada wewnętrzny mechanizm gwarantujący spójność kosztów i stanów magazynowych, uruchamiany przy każdej operacji na wydatkach.

*   **Dodanie wydatku (Funkcja: `add_expense_and_sync`):**
    Jeśli użytkownik tworzy wydatek na 500 zł (10 szt.) i podpina go pod Materiał A:
    1. Rekord ląduje w tabeli `expenses`.
    2. W tabeli `materials` dla Materiału A następuje UPDATE: `cost_actual` sumuje wszystkie poprzednie wydatki + te nowe 500 zł. `quantity_received` powiększa się o 10 sztuk.
*   **Anulowanie wydatku (Funkcja: `delete_expense_and_sync`):**
    Jeśli użytkownik anuluje wydatek (Miękkie usunięcie: `is_deleted = 1`):
    1. W tabeli `materials` dla Materiału A następuje UPDATE: aplikacja od nowa przelicza `cost_actual` ignorując usunięty wydatek. Zmniejsza również `quantity_received` o anulowaną ilość.

---

## 5. Scoring Engine (Wersja v2.0 - Odporna na pustki)

Algorytm sortujący akcje na Dashboardzie, wylistowujący top 5 najwyżej punktowanych priorytetów. Ignoruje rekordy oznaczone jako `is_deleted = 1`.

*   **Brak Daty (`needed_by` = NULL):**
    *   Jeśli Materiał nie ma określonej daty, **NIE WYRZUCA** alarmu o opóźnieniu. Generuje jedynie prośbę o uzupełnienie (Waga: 10 pkt).
*   **Wymogi Ekipy (`crew_requests`):**
    *   "is_blocker" = Prawda ➡️ **+200 pkt**
    *   Termin na dzisiaj/jutro ➡️ **+150 pkt**
    *   Termin za 2-4 dni ➡️ **+100 pkt**
*   **Materiały (`materials`):**
    *   `order_deadline` = (`needed_by` MINUS `lead_time_days`).
    *   Termin zamówienia mija dziś lub był wczoraj ➡️ **+150 pkt**
    *   Zostały 1-3 dni do zamówienia ➡️ **+80 pkt**
*   **Decyzje (`decisions`):**
    *   Wpływ "Krytyczny" i termin do 3 dni ➡️ **+120 pkt**

---

## 6. Przegląd Ekranów (Moduły)

1.  **Dashboard:** Mózg operacji (Wskaźniki gotowości, TOP 5 akcji z Scoringu, Zgłoszenia ekipy, Lista dostępnych materiałów dla ekipy na budowie).
2.  **Start Remontu:** Kreator pomieszczeń używający mechaniki zabezpieczającej błędy powtórzeń (`ON CONFLICT`).
3.  **Materiały i sprzęty:** Narzędzie magazynowe oparte o `st.data_editor` (edycja z poziomu tabeli checkboxów i lokalizacji). Zawiera narzędzie do archiwizacji (soft delete).
4.  **Zadania:** Śledzenie postępu i priorytetów (wierszowa edycja).
5.  **Ekipa (Widok Inwestora):** Odbiór zgłoszeń (zapotrzebowań) od ekipy budowlanej (wierszowa edycja, zamykanie zgłoszeń).
6.  **Wydatki:** Miejsce księgowania faktur i sprzęgania ich z materiałami, dzięki czemu system utrzymuje aktualne ceny.
7.  **(Zablokowane Widoki w toku):** Decyzje, Ryzyka, Dziennik, Ustawienia.
