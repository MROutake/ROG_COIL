# Berechnungsmodell für PCB-Rogowski-Spulen

> Dokumentation aller Berechnungsformeln und physikalischen Modelle,
> die in `pcb_rogowski` zur Bestimmung der äquivalenten Schaltungsparameter
> (L, C, R) einer PCB-Rogowski-Spule verwendet werden.

---

## 1  Ersatzschaltbild

Die PCB-Rogowski-Spule wird als **paralleles RLC-Netzwerk** modelliert —
eine verlustbehaftete Induktivität mit parasitärer Parallelkapazität:

```
           R_s(f)    L
    +--+--/\/\/--UUUUU--+
    |  |                 |
    |  +------||--------+     C  (parallel)
    |  |                 |
    +--+-----------------+
```

Die komplexe Impedanz lautet:

$$
Z(f) = \frac{R_s(f) + j\omega L}{1 - \omega^2 L C + j\omega R_s(f) C}
$$

mit $\omega = 2\pi f$.

**Frequenzverhalten:**

| Bereich | Impedanz | Phase |
|---------|----------|-------|
| $f \ll f_\text{res}$ | $Z \approx R_s + j\omega L$ | ≈ +90° (induktiv) |
| $f = f_\text{res}$ | $\lvert Z\rvert$ maximal | 0° (Resonanz) |
| $f \gg f_\text{res}$ | $Z \approx \frac{1}{j\omega C}$ | ≈ −90° (kapazitiv) |

Resonanzfrequenz:

$$
f_\text{res} = \frac{1}{2\pi\sqrt{LC}}
$$

---

## 2  Induktivität $L$

**Quelldatei:** `src/pcb_rogowski/domain/coil/inductance.py`

### 2.1  Gesamtmodell

$$
L_C = L_\text{self} + L_\text{vias} \;\left[+ \; L_\text{mutual}\right]
$$

| Beitrag | Beschreibung |
|---------|-------------|
| $L_\text{self}$ | Summe der Eigeninduktivitäten aller Segmente (Winding + Return) |
| $L_\text{vias}$ | Via-Induktivität (alle Vias in Serie) |
| $L_\text{mutual}$ | PEEC-Kreuzterme (nur wenn Pitch-Kriterium verletzt, s. §2.4) |

### 2.2  Eigeninduktivität eines Leiterbahnstücks (Ruehli / Lorenz)

Jedes gerade Leiterbahnsegment $i$ mit Länge $l_i$, Breite $W$ und
Kupferdicke $T$ hat die Freiraum-Eigeninduktivität:

$$
L_{\text{self},i} = \frac{\mu_0 \, l_i}{2\pi}
\left[\ln\!\left(\frac{2\,l_i}{W+T}\right) + 0{,}5 + 0{,}2235\,\frac{W+T}{l_i}\right]
$$

- Diese Formel gilt für einen isolierten, geraden Leiter mit rechteckigem
  Querschnitt im Freiraum (kein Rückleiter / Schirm eingerechnet).

Die Gesamt-Eigeninduktivität ergibt sich als Summe über alle
Windungs- und Rückleitersegmente:

$$
L_\text{self} = \sum_{i \in \text{winding}} L_{\text{self},i}
              + \sum_{j \in \text{return}} L_{\text{self},j}
$$

### 2.3  Via-Induktivität

Jeder Via (Durchkontaktierung) mit Höhe $h$ und Bohrungsdurchmesser $d$
hat die Eigeninduktivität:

$$
L_\text{via} = \frac{\mu_0 \, h}{2\pi}
\left(1 + \ln\frac{4h}{d}\right)
$$

Die Gesamt-Via-Induktivität aller $N$ Vias in Serie:

$$
L_\text{vias} = N \cdot L_\text{via}
$$

### 2.4  Pitch-Kriterium und Mutual-Korrektur

Der Windungsabstand (Pitch) $p$ bestimmt, ob gegenseitige Induktivitäten
zwischen benachbarten Segmenten berücksichtigt werden müssen:

$$
\frac{p}{W} \geq 8 \quad \Rightarrow \quad
\text{Kopplung vernachlässigbar, } L_\text{mutual} = 0
$$



**Berechnung der Mutuals (PEEC):**

Das Neumann-Integral für zwei Segmente $i$ und $j$ wird mit
2×2 Gauß-Legendre-Quadratur ausgewertet:

$$
M_{ij} = \frac{\mu_0}{4\pi} \int_{l_i} \int_{l_j}
\frac{\hat{t}_i \cdot \hat{t}_j}{\lvert\mathbf{r}_i - \mathbf{r}_j\rvert}
\,dl_i \,dl_j
$$

Die Mutual-Korrektur ergibt sich aus:

$$
L_\text{mutual} = \boldsymbol{\gamma}^\top \mathbf{M} \boldsymbol{\gamma}
- \sum_i \gamma_i^2 \, M_{ii}
$$

wobei $\gamma_i$ der Wirksamkeitsfaktor pro Segment ist:

| Segmenttyp | $\gamma$ |
|-----------|----------|
| Winding, $\sigma = +1$ | $+1$ (Stromrichtung vorwärts) |
| Winding, $\sigma = -1$ | $-1$ (Stromrichtung rückwärts, Doppel-Rogowski) |
| Return | $-1$ (Rückleiter kompensiert Fluss) |
| Connection | $0$ (Zuleitung, kein Beitrag) |

### 2.5  Validierung

Vergleich des berechneten $L$ mit Bode100-Referenzwerten:

| Design | $L_\text{Ref}$ [µH] | $L_\text{Geom}$ [µH] | Fehler | p/W |
|--------|---------------------|----------------------|--------|-----|
| D2 | 0,399 | 0,379 | −4,9 % | 10–14 |
| D3 | 0,411 | 0,386 | −6,0 % | 10–14 |
| D1 | 2,006 | 2,126 | +6,0 % | 2,5 |


---

## 3  Kapazität $C$

**Quelldatei:** `src/pcb_rogowski/domain/coil/capacitance.py`

### 3.1  Gesamtmodell (ohne Grundebene)

$$
C_\text{total} = C_\text{coupling} + C_\text{interturn} + C_\text{via}
$$

| Beitrag | Beschreibung |
|---------|-------------|
| $C_\text{coupling}$ | Kopplung Windungssegment ↔ benachbarte Innenlage durch $H_\text{diel}$ |
| $C_\text{interturn}$ | Kapazität zwischen benachbarten Windungszähnen auf gleicher Lage |
| $C_\text{via}$ | Via-Kapazität (Zylinderkondensator) |


### 3.2  Coupling-Kapazität $C_\text{coupling}$

Jedes Windungssegment auf der Oberseite (Top) koppelt kapazitiv durch
das Dielektrikum ($H_\text{diel}$) zur darunterliegenden Kupferlage
(Return-Ring / andere Windungen).

Parallelplatten-Näherung pro Segment:

$$
C_{\text{coupling},i} = \varepsilon_0 \, \varepsilon_r \cdot \frac{W_i \cdot l_i}{H_\text{diel}}
$$

Summe über alle Windungssegmente:

$$
C_\text{coupling} = \sum_i C_{\text{coupling},i}
$$

**Parameter:**
- $\varepsilon_0 = 8{,}854 \times 10^{-12}$ F/m
- $\varepsilon_r = 4{,}8$ (FR-4)
- $H_\text{diel} = 0{,}320$ mm (Abstand Top ↔ Mid-Layer 1)
- $W_i$ = Leiterbreite des Segments [m]
- $l_i$ = Segmentlänge [m]

### 3.3  Interturn-Kapazität $C_\text{interturn}$

Benachbarte Windungszähne auf derselben Lage bilden seitliche
Plattenkondensatoren.  Die Kapazität pro Paar enthält einen
Parallelplatten-Anteil und eine Randfeld-Korrektur (konforme Abbildung):

$$
C_\text{pair} = \varepsilon_0 \, \varepsilon_r \cdot l
\left(\frac{W}{g} + \frac{1}{\pi}\ln\!\left(1 + \frac{2W}{g}\right)\right)
$$

- $l$ = gemeinsame Kopplungslänge (Median der Segmentlängen)
- $W$ = mittlere Leiterbreite
- $g$ = Spalt zwischen den Leitern (typisch 0,2 mm)

$$
C_\text{interturn} = N_\text{Paare} \cdot C_\text{pair}
$$

$N_\text{Paare}$ wird automatisch durch Abstandsanalyse der
Segmentmittelpunkte bestimmt (Schwelle: 0,4 mm).

### 3.4  Via-Kapazität $C_\text{via}$

Jeder Via hat eine parasitäre Kapazität gegenüber dem umgebenden
Dielektrikum / Kupferflächen:

$$
C_\text{via} = N_\text{Vias} \cdot c_\text{via}
$$

mit $c_\text{via} \approx 30$ fF pro Via (Erfahrungswert für
Standard-PCB-Vias mit $d = 0{,}2$–$0{,}3$ mm).

### 3.5  Validierung

| Design | $C_\text{Ref}$ [pF] | $C_\text{Geom}$ [pF] | Fehler |
|--------|---------------------|----------------------|--------|
| D2 | 12,31 | 13,30 | +8,0 % |
| D3 | 12,90 | 13,47 | +4,4 % |
| D1 | 86,09 | 58,88 | −31,6 % |


---

## 4  Widerstand $R_s(f)$

**Quelldatei:** `src/pcb_rogowski/domain/coil/skin.py`

### 4.1  Gesamtmodell

$$
R_s(f) = R_\text{track}(f) + R_\text{via}(f) + R_\text{contact}
$$

### 4.2  Leiterbahn-Widerstand $R_\text{track}(f)$

Basiert auf der frequenzabhängigen Skin-Tiefe:

$$
\delta(f) = \sqrt{\frac{2\rho}{\omega\mu_0}}
$$

mit $\rho = 1{,}72 \times 10^{-8}\;\Omega\text{m}$ (Kupfer, 20 °C).

Der effektive Leiterquerschnitt hängt vom Verhältnis $\delta$ zu $T/2$ ab:

$$
A_\text{eff} = \begin{cases}
W \cdot T & \text{wenn } \delta \geq T/2 \quad (\text{DC-Näherung}) \\
2\delta(W + T) & \text{wenn } \delta < T/2 \quad (\text{Skin-dominiert})
\end{cases}
$$

Widerstand pro Segment:

$$
R_{\text{track},i}(f) = \frac{\rho \cdot l_i}{A_{\text{eff},i}(f)}
$$

### 4.3  Proximity-Korrektur

Ein einfaches Potenz-Modell:

$$
R_\text{prox}(f) = R_\text{track}(f) \cdot k_\text{prox} \cdot \sqrt{\frac{f}{f_0}}
$$

mit $k_\text{prox}$ und $f_0 = 1$ MHz als Fit-Parameter.

### 4.4  Via-Widerstand $R_\text{via}(f)$

Die Via-Plating bildet einen Hohlzylinder mit effektiver Dicke
$t_\text{eff} = \min(t_\text{plating}, \delta)$:

$$
A_\text{plating} = \pi \cdot d_\text{via} \cdot t_\text{eff}
$$

$$
R_\text{via} = N_\text{Vias} \cdot \frac{\rho \cdot h_\text{via}}{A_\text{plating}}
$$

**Typische Werte:**
- $t_\text{plating} = 25\;\mu\text{m}$ (1 oz Standard-PCB)
- $d_\text{via} = 0{,}2$–$0{,}3$ mm
- $h_\text{via} = 1{,}12$ mm (Gesamtdicke)

### 4.5  Fit-Modell für $R_s(f)$ im Impedanzfit

Im Bode100-Fit wird der Widerstand vereinfacht parametrisiert:

$$
R_s(f) = R_\text{dc} + k_\text{skin}\sqrt{f} + k_\text{prox}\frac{f}{f_0}
$$

Die Parameter $R_\text{dc}$, $k_\text{skin}$ und $k_\text{prox}$ werden
zusammen mit $L$ und $C$ gefittet (5 Fit-Parameter).

---

## 5  Bode100-Fit

**Quelldatei:** `src/pcb_rogowski/domain/coil/fitting.py`

### 5.1  Messdaten

Bode100-CSV-Dateien enthalten frequenzaufgelöste Impedanzmessungen:
$\text{Re}(Z)$, $\text{Im}(Z)$, $|Z|$, $\varphi(Z)$.

### 5.2  Startwertbestimmung (Auto-Init)

Die Startwerte für den Fit werden automatisch aus den Messdaten geschätzt
(`estimate_from_data`):

**Induktivität** $L_0$:

$$
L_0 = \text{Median}\left(\frac{\text{Im}(Z)}{2\pi f}\right)
\quad \text{bei } f \leq 2\;\text{MHz}
$$

**Widerstand** $R_0$:

$$
R_0 = \text{Median}\left(|\text{Re}(Z)|\right) \quad \text{bei } f \leq 2\;\text{MHz}
$$

**Kapazität** $C_0$, zwei Methoden:

1. **Nulldurchgang von $\text{Im}(Z)$:**
   Wenn $\text{Im}(Z)$ das Vorzeichen wechselt (pos → neg), wird die
   Resonanzfrequenz $f_\text{res}$ linear interpoliert:

   $$C_0 = \frac{1}{4\pi^2 f_\text{res}^2 \, L_0}$$

2. **Hochfrequenz-Verstärkung** (falls kein Nulldurchgang im Messbereich):

   $$C_0 = \frac{1 - \omega L_0 / \text{Im}(Z)}{\omega^2 L_0}
   \quad \text{bei hohen } f$$

### 5.3  Fit-Algorithmus

**Methode:** `scipy.optimize.least_squares` mit Trust-Region-Reflective (TRF)

**Fit-Parameter:**

$$\mathbf{x} = \begin{bmatrix} L & R_\text{dc} & k_\text{skin} & k_\text{prox} & C \end{bmatrix}$$

**Residuum (log-Betrag + Phase):**

$$
\mathbf{r} = \begin{bmatrix}
\ln|Z_\text{mod}| - \ln|Z_\text{mess}| \\[4pt]
w_\text{imag} \cdot \big(\varphi(Z_\text{mod}) - \varphi(Z_\text{mess})\big)
\end{bmatrix}
$$


**Grenzen (bounds):**

| Parameter | Untergrenze | Obergrenze |
|-----------|------------|------------|
| $L$ | $0{,}05 \cdot L_0$ | $10 \cdot L_0$ |
| $R_\text{dc}$ | $0{,}1$ mΩ | 500 Ω |
| $k_\text{skin}$ | 0 | 0,05 Ω/√Hz |
| $k_\text{prox}$ | 0 | 0,2 |
| $C$ | 0,1 pF | 10 nF |

**Skalierung:** `x_scale = [L_0, R_0, 1e-4, 0.1, C_0]` — kritisch für
korrekte numerische Gradienten bei stark unterschiedlichen Größenordnungen
($L \sim 10^{-6}$, $C \sim 10^{-12}$).

### 5.4  Güte-Metriken

- **RMSE Re(Z):** $\sqrt{\text{mean}\big((\text{Re}(Z_\text{fit}) - \text{Re}(Z_\text{mess}))^2\big)}$ [Ω]
- **RMSE Im(Z):** analog [Ω]
- **RMSE |Z|:** $\sqrt{\text{mean}\left(\left(\frac{|Z_\text{fit}| - |Z_\text{mess}|}{|Z|_\text{max}}\right)^2\right)} \cdot 100$ [%]

### 5.5  Fit-Ergebnisse

| Design | $L$ [µH] | $R_\text{dc}$ [Ω] | $C$ [pF] | RMSE |Z| |
|--------|----------|-------------------|----------|---------|
| D1 | 2,006 | 5,129 | 85,82 | 1,54 % |
| D2 | 0,399 | 2,026 | 12,30 | 0,20 % |
| D3 | 0,411 | 2,111 | 12,89 | 0,19 % |

---

## 6  PCB-Stackup

**Konfigurationsdatei:** `configs/stackup_design03.yaml`

4-Lagen-Aufbau (identisch für alle drei Designs):

```
  ┌────────────────────┐
  │    Top Layer       │  T = 35,56 µm  (1 oz Cu)
  ├────────────────────┤
  │   Dielectric 1     │  H = 0,320 mm  εr = 4,8
  ├────────────────────┤
  │   Mid-Layer 1      │  T = 35,56 µm
  ├────────────────────┤
  │   Dielectric 2     │  H = 0,320 mm  εr = 4,8
  ├────────────────────┤
  │   Mid-Layer 2      │  T = 35,56 µm
  ├────────────────────┤
  │   Dielectric 3     │  H = 0,320 mm  εr = 4,8
  ├────────────────────┤
  │   Bottom Layer     │  T = 35,56 µm
  └────────────────────┘
       Gesamtdicke = 1,123 mm
```

**Relevante Kenngrößen:**

| Symbol | Wert | Beschreibung |
|--------|------|-------------|
| $T$ | 35,56 µm | Kupferdicke (1 oz) |
| $H_\text{diel}$ | 0,320 mm | Abstand benachbarter Kupferlagen |
| $\varepsilon_r$ | 4,8 | Relative Permittivität FR-4 |
| $h_\text{total}$ | 1,123 mm | Gesamtdicke der Leiterplatte |

---

## 7  Segmentklassifikation und Wirksamkeitsvektor $\boldsymbol{\gamma}$

**Quelldatei:** `scripts/fit_bode100.py`, Funktion `_build_segments()`

Jedes Leiterbahnsegment wird anhand der manuellen Klassifikation
(YAML-Datei pro Design) einer Rolle zugeordnet:

| Rolle | Gamma $\gamma$ | Physik |
|-------|----------------|--------|
| **winding** ($\sigma = +1$) | $+1$ | Windung, Strom in Vorwärtsrichtung |
| **winding** ($\sigma = -1$) | $-1$ | Windung, Strom in Rückwärtsrichtung (Doppel-Rogowski: untere Hälfte) |
| **return** | $-1$ | Rückleiter, kompensiert den Windungsfluss |
| **connection** | $0$ | Zuleitung, kein Beitrag zur Induktivität |

### 7.1  Sigma und Doppel-Rogowski

Beim Doppel-Rogowski (Design 1) wickeln die Windungen in der **oberen
Hälfte** im Uhrzeigersinn ($\sigma = +1$) und in der **unteren Hälfte**
gegen den Uhrzeigersinn ($\sigma = -1$).  Der Y-Schwellwert (Trennlinie)
wird aus der geometrischen Mitte der Windungssegmente bestimmt.

### 7.2  Via-Statistik pro Design

| Design | Vias | $d_\text{via}$ | Windung | Return |
|--------|------|---------------|---------|--------|
| D1 | 408 | 0,300 mm | 379 Seg. | 28 Seg. |
| D2 | 102 | 0,200 mm | 196 Seg. | 190 Seg. |
| D3 | 102 | 0,200 mm | 200 Seg. | 194 Seg. |

---

## 8  Gesamtübersicht: Vergleich Geometrie vs. Messung

| Parameter | D1 Geom | D1 Ref | Err | D2 Geom | D2 Ref | Err | D3 Geom | D3 Ref | Err |
|-----------|---------|--------|-----|---------|--------|-----|---------|--------|-----|
| $L$ [µH] | 2,126 | 2,006 | +6,0 % | 0,379 | 0,399 | −4,9 % | 0,386 | 0,411 | −6,0 % |
| $C$ [pF] | 58,9 | 86,1 | −31,6 % | 13,3 | 12,3 | +8,0 % | 13,5 | 12,9 | +4,4 % |
| $R_\text{dc}$ [Ω] | 5,12 | 5,20 | −1,6 % | 1,46 | 2,03 | −27,8 % | 1,46 | 2,12 | −30,8 % |
| $f_\text{res}$ [MHz] | 14,2 | 12,1 | +17,4 % | 70,9 | 71,8 | −1,3 % | 69,8 | 69,1 | +1,0 % |

---

## 9  Physikalische Konstanten

| Konstante | Symbol | Wert |
|-----------|--------|------|
| Vakuumpermeabilität | $\mu_0$ | $1{,}2566 \times 10^{-6}$ H/m |
| Vakuumpermittivität | $\varepsilon_0$ | $8{,}854 \times 10^{-12}$ F/m |
| Spez. Widerstand Kupfer (20 °C) | $\rho_\text{Cu}$ | $1{,}72 \times 10^{-8}$ Ω·m |

---


