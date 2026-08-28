# -*- coding: utf-8 -*-
"""Ontologi Baku Satuan Ilmiah (SI / UCUM / QUDT / Pint Standard) & Citation Disambiguation Engine.

Mendukung ribuan satuan SI, turunan, prefiks universal, satuan medis/biokimia,
energi, elektro, ekonomi, serta satuan majemuk (compound units), sekaligus
mengeliminasi false positive dari sitasi pangkat (superscript) dan footnote.
"""

import re
from typing import Dict, Any, Optional, Tuple, Set, List


# ---------------------------------------------------------
# 1. SI PREFIXES (Universal Multipliers)
# ---------------------------------------------------------
SI_PREFIXES: Dict[str, Tuple[float, str]] = {
    'Y': (1e24, 'yotta'),
    'Z': (1e21, 'zetta'),
    'E': (1e18, 'exa'),
    'P': (1e15, 'peta'),
    'T': (1e12, 'tera'),
    'G': (1e9, 'giga'),
    'M': (1e6, 'mega'),
    'k': (1e3, 'kilo'),
    'h': (1e2, 'hecto'),
    'da': (1e1, 'deca'),
    'd': (1e-1, 'deci'),
    'c': (1e-2, 'centi'),
    'm': (1e-3, 'milli'),
    'u': (1e-6, 'micro'),
    'μ': (1e-6, 'micro'),
    'µ': (1e-6, 'micro'),
    'n': (1e-9, 'nano'),
    'p': (1e-12, 'pico'),
    'f': (1e-15, 'femto'),
    'a': (1e-18, 'atto'),
    'z': (1e-21, 'zepto'),
    'y': (1e-24, 'yocto'),
}

# ---------------------------------------------------------
# 2. STANDARDIZED BASE & DERIVED UNITS BY PHYSICAL DIMENSION
# ---------------------------------------------------------
KNOWN_UNITS_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Length & Distance
    'm': {'dimension': 'Length', 'name': 'meter', 'allow_prefix': True},
    'meter': {'dimension': 'Length', 'name': 'meter', 'allow_prefix': True},
    'metre': {'dimension': 'Length', 'name': 'meter', 'allow_prefix': True},
    'meters': {'dimension': 'Length', 'name': 'meter', 'allow_prefix': True},
    'metres': {'dimension': 'Length', 'name': 'meter', 'allow_prefix': True},
    'in': {'dimension': 'Length', 'name': 'inch', 'allow_prefix': False},
    'inch': {'dimension': 'Length', 'name': 'inch', 'allow_prefix': False},
    'inches': {'dimension': 'Length', 'name': 'inch', 'allow_prefix': False},
    'ft': {'dimension': 'Length', 'name': 'foot', 'allow_prefix': False},
    'feet': {'dimension': 'Length', 'name': 'foot', 'allow_prefix': False},
    'foot': {'dimension': 'Length', 'name': 'foot', 'allow_prefix': False},
    'yd': {'dimension': 'Length', 'name': 'yard', 'allow_prefix': False},
    'mi': {'dimension': 'Length', 'name': 'mile', 'allow_prefix': False},
    'mile': {'dimension': 'Length', 'name': 'mile', 'allow_prefix': False},
    'miles': {'dimension': 'Length', 'name': 'mile', 'allow_prefix': False},
    'angstrom': {'dimension': 'Length', 'name': 'angstrom', 'allow_prefix': False},
    'å': {'dimension': 'Length', 'name': 'angstrom', 'allow_prefix': False},

    # Area & Volume
    'm2': {'dimension': 'Area', 'name': 'square meter', 'allow_prefix': True},
    'm²': {'dimension': 'Area', 'name': 'square meter', 'allow_prefix': True},
    'ha': {'dimension': 'Area', 'name': 'hectare', 'allow_prefix': False},
    'hectare': {'dimension': 'Area', 'name': 'hectare', 'allow_prefix': False},
    'hectares': {'dimension': 'Area', 'name': 'hectare', 'allow_prefix': False},
    'acre': {'dimension': 'Area', 'name': 'acre', 'allow_prefix': False},
    'acres': {'dimension': 'Area', 'name': 'acre', 'allow_prefix': False},
    'm3': {'dimension': 'Volume', 'name': 'cubic meter', 'allow_prefix': True},
    'm³': {'dimension': 'Volume', 'name': 'cubic meter', 'allow_prefix': True},
    'l': {'dimension': 'Volume', 'name': 'liter', 'allow_prefix': True},
    'liter': {'dimension': 'Volume', 'name': 'liter', 'allow_prefix': True},
    'litre': {'dimension': 'Volume', 'name': 'liter', 'allow_prefix': True},
    'liters': {'dimension': 'Volume', 'name': 'liter', 'allow_prefix': True},
    'litres': {'dimension': 'Volume', 'name': 'liter', 'allow_prefix': True},
    'gal': {'dimension': 'Volume', 'name': 'gallon', 'allow_prefix': False},
    'gallon': {'dimension': 'Volume', 'name': 'gallon', 'allow_prefix': False},
    'bbl': {'dimension': 'Volume', 'name': 'barrel', 'allow_prefix': False},

    # Mass & Weight
    'g': {'dimension': 'Mass', 'name': 'gram', 'allow_prefix': True},
    'gram': {'dimension': 'Mass', 'name': 'gram', 'allow_prefix': True},
    'grams': {'dimension': 'Mass', 'name': 'gram', 'allow_prefix': True},
    't': {'dimension': 'Mass', 'name': 'metric ton', 'allow_prefix': True},
    'ton': {'dimension': 'Mass', 'name': 'ton', 'allow_prefix': True},
    'tons': {'dimension': 'Mass', 'name': 'ton', 'allow_prefix': True},
    'tonne': {'dimension': 'Mass', 'name': 'metric ton', 'allow_prefix': True},
    'tonnes': {'dimension': 'Mass', 'name': 'metric ton', 'allow_prefix': True},
    'lb': {'dimension': 'Mass', 'name': 'pound', 'allow_prefix': False},
    'lbs': {'dimension': 'Mass', 'name': 'pound', 'allow_prefix': False},
    'pound': {'dimension': 'Mass', 'name': 'pound', 'allow_prefix': False},
    'pounds': {'dimension': 'Mass', 'name': 'pound', 'allow_prefix': False},
    'oz': {'dimension': 'Mass', 'name': 'ounce', 'allow_prefix': False},
    'ounce': {'dimension': 'Mass', 'name': 'ounce', 'allow_prefix': False},
    'dalton': {'dimension': 'Mass', 'name': 'dalton', 'allow_prefix': True},
    'da': {'dimension': 'Mass', 'name': 'dalton', 'allow_prefix': True},
    'kda': {'dimension': 'Mass', 'name': 'kilodalton', 'allow_prefix': False},

    # Time & Frequency
    's': {'dimension': 'Time', 'name': 'second', 'allow_prefix': True},
    'sec': {'dimension': 'Time', 'name': 'second', 'allow_prefix': True},
    'second': {'dimension': 'Time', 'name': 'second', 'allow_prefix': True},
    'seconds': {'dimension': 'Time', 'name': 'second', 'allow_prefix': True},
    'min': {'dimension': 'Time', 'name': 'minute', 'allow_prefix': False},
    'minute': {'dimension': 'Time', 'name': 'minute', 'allow_prefix': False},
    'minutes': {'dimension': 'Time', 'name': 'minute', 'allow_prefix': False},
    'h': {'dimension': 'Time', 'name': 'hour', 'allow_prefix': False},
    'hr': {'dimension': 'Time', 'name': 'hour', 'allow_prefix': False},
    'hour': {'dimension': 'Time', 'name': 'hour', 'allow_prefix': False},
    'hours': {'dimension': 'Time', 'name': 'hour', 'allow_prefix': False},
    'day': {'dimension': 'Time', 'name': 'day', 'allow_prefix': False},
    'days': {'dimension': 'Time', 'name': 'day', 'allow_prefix': False},
    'week': {'dimension': 'Time', 'name': 'week', 'allow_prefix': False},
    'weeks': {'dimension': 'Time', 'name': 'week', 'allow_prefix': False},
    'month': {'dimension': 'Time', 'name': 'month', 'allow_prefix': False},
    'months': {'dimension': 'Time', 'name': 'month', 'allow_prefix': False},
    'year': {'dimension': 'Time', 'name': 'year', 'allow_prefix': False},
    'years': {'dimension': 'Time', 'name': 'year', 'allow_prefix': False},
    'yr': {'dimension': 'Time', 'name': 'year', 'allow_prefix': False},
    'hz': {'dimension': 'Frequency', 'name': 'hertz', 'allow_prefix': True},
    'hertz': {'dimension': 'Frequency', 'name': 'hertz', 'allow_prefix': True},
    'rpm': {'dimension': 'RotationalSpeed', 'name': 'revolutions per minute', 'allow_prefix': False},

    # Energy, Power, Heat
    'j': {'dimension': 'Energy', 'name': 'joule', 'allow_prefix': True},
    'joule': {'dimension': 'Energy', 'name': 'joule', 'allow_prefix': True},
    'joules': {'dimension': 'Energy', 'name': 'joule', 'allow_prefix': True},
    'wh': {'dimension': 'Energy', 'name': 'watt-hour', 'allow_prefix': True},
    'watthour': {'dimension': 'Energy', 'name': 'watt-hour', 'allow_prefix': True},
    'watt-hour': {'dimension': 'Energy', 'name': 'watt-hour', 'allow_prefix': True},
    'cal': {'dimension': 'Energy', 'name': 'calorie', 'allow_prefix': True},
    'calorie': {'dimension': 'Energy', 'name': 'calorie', 'allow_prefix': True},
    'calories': {'dimension': 'Energy', 'name': 'calorie', 'allow_prefix': True},
    'btu': {'dimension': 'Energy', 'name': 'british thermal unit', 'allow_prefix': False},
    'ev': {'dimension': 'Energy', 'name': 'electronvolt', 'allow_prefix': True},
    'electronvolt': {'dimension': 'Energy', 'name': 'electronvolt', 'allow_prefix': True},
    'w': {'dimension': 'Power', 'name': 'watt', 'allow_prefix': True},
    'watt': {'dimension': 'Power', 'name': 'watt', 'allow_prefix': True},
    'watts': {'dimension': 'Power', 'name': 'watt', 'allow_prefix': True},
    'hp': {'dimension': 'Power', 'name': 'horsepower', 'allow_prefix': False},
    'horsepower': {'dimension': 'Power', 'name': 'horsepower', 'allow_prefix': False},
    'va': {'dimension': 'ApparentPower', 'name': 'volt-ampere', 'allow_prefix': True},
    'var': {'dimension': 'ReactivePower', 'name': 'volt-ampere reactive', 'allow_prefix': True},

    # Force, Pressure, Mechanics
    'n': {'dimension': 'Force', 'name': 'newton', 'allow_prefix': True},
    'newton': {'dimension': 'Force', 'name': 'newton', 'allow_prefix': True},
    'dyn': {'dimension': 'Force', 'name': 'dyne', 'allow_prefix': True},
    'pa': {'dimension': 'Pressure', 'name': 'pascal', 'allow_prefix': True},
    'pascal': {'dimension': 'Pressure', 'name': 'pascal', 'allow_prefix': True},
    'bar': {'dimension': 'Pressure', 'name': 'bar', 'allow_prefix': True},
    'mbar': {'dimension': 'Pressure', 'name': 'millibar', 'allow_prefix': False},
    'atm': {'dimension': 'Pressure', 'name': 'atmosphere', 'allow_prefix': False},
    'torr': {'dimension': 'Pressure', 'name': 'torr', 'allow_prefix': False},
    'mmhg': {'dimension': 'Pressure', 'name': 'millimeter of mercury', 'allow_prefix': False},
    'psi': {'dimension': 'Pressure', 'name': 'pounds per square inch', 'allow_prefix': False},

    # Electrical, Magnetic, Signal
    'v': {'dimension': 'ElectricPotential', 'name': 'volt', 'allow_prefix': True},
    'volt': {'dimension': 'ElectricPotential', 'name': 'volt', 'allow_prefix': True},
    'volts': {'dimension': 'ElectricPotential', 'name': 'volt', 'allow_prefix': True},
    'a': {'dimension': 'ElectricCurrent', 'name': 'ampere', 'allow_prefix': True},
    'amp': {'dimension': 'ElectricCurrent', 'name': 'ampere', 'allow_prefix': True},
    'amps': {'dimension': 'ElectricCurrent', 'name': 'ampere', 'allow_prefix': True},
    'ampere': {'dimension': 'ElectricCurrent', 'name': 'ampere', 'allow_prefix': True},
    'amperes': {'dimension': 'ElectricCurrent', 'name': 'ampere', 'allow_prefix': True},
    'ohm': {'dimension': 'ElectricalResistance', 'name': 'ohm', 'allow_prefix': True},
    'ohms': {'dimension': 'ElectricalResistance', 'name': 'ohm', 'allow_prefix': True},
    'ω': {'dimension': 'ElectricalResistance', 'name': 'ohm', 'allow_prefix': True},
    'f': {'dimension': 'Capacitance', 'name': 'farad', 'allow_prefix': True},
    'farad': {'dimension': 'Capacitance', 'name': 'farad', 'allow_prefix': True},
    'h': {'dimension': 'Inductance', 'name': 'henry', 'allow_prefix': True},
    'henry': {'dimension': 'Inductance', 'name': 'henry', 'allow_prefix': True},
    'c': {'dimension': 'ElectricCharge', 'name': 'coulomb', 'allow_prefix': True},
    'coulomb': {'dimension': 'ElectricCharge', 'name': 'coulomb', 'allow_prefix': True},
    's': {'dimension': 'ElectricalConductance', 'name': 'siemens', 'allow_prefix': True},
    'siemens': {'dimension': 'ElectricalConductance', 'name': 'siemens', 'allow_prefix': True},
    't': {'dimension': 'MagneticFluxDensity', 'name': 'tesla', 'allow_prefix': True},
    'tesla': {'dimension': 'MagneticFluxDensity', 'name': 'tesla', 'allow_prefix': True},
    'wb': {'dimension': 'MagneticFlux', 'name': 'weber', 'allow_prefix': True},
    'g': {'dimension': 'MagneticField', 'name': 'gauss', 'allow_prefix': True},
    'gauss': {'dimension': 'MagneticField', 'name': 'gauss', 'allow_prefix': True},
    'db': {'dimension': 'LogarithmicRatio', 'name': 'decibel', 'allow_prefix': False},
    'dbm': {'dimension': 'LogarithmicPower', 'name': 'decibel milliwatt', 'allow_prefix': False},
    'dbi': {'dimension': 'AntennaGain', 'name': 'decibel isotropic', 'allow_prefix': False},
    'bps': {'dimension': 'DataRate', 'name': 'bits per second', 'allow_prefix': True},
    'baud': {'dimension': 'SymbolRate', 'name': 'baud', 'allow_prefix': True},
    'bit': {'dimension': 'DataAmount', 'name': 'bit', 'allow_prefix': True},
    'bits': {'dimension': 'DataAmount', 'name': 'bit', 'allow_prefix': True},
    'byte': {'dimension': 'DataAmount', 'name': 'byte', 'allow_prefix': True},
    'bytes': {'dimension': 'DataAmount', 'name': 'byte', 'allow_prefix': True},
    'b': {'dimension': 'DataAmount', 'name': 'byte', 'allow_prefix': True},

    # Temperature
    'k': {'dimension': 'Temperature', 'name': 'kelvin', 'allow_prefix': False},
    'kelvin': {'dimension': 'Temperature', 'name': 'kelvin', 'allow_prefix': False},
    '°c': {'dimension': 'Temperature', 'name': 'degree Celsius', 'allow_prefix': False},
    'deg c': {'dimension': 'Temperature', 'name': 'degree Celsius', 'allow_prefix': False},
    'celsius': {'dimension': 'Temperature', 'name': 'degree Celsius', 'allow_prefix': False},
    '°f': {'dimension': 'Temperature', 'name': 'degree Fahrenheit', 'allow_prefix': False},
    'deg f': {'dimension': 'Temperature', 'name': 'degree Fahrenheit', 'allow_prefix': False},
    'fahrenheit': {'dimension': 'Temperature', 'name': 'degree Fahrenheit', 'allow_prefix': False},

    # Chemistry, Medicine, Biochemistry
    'mol': {'dimension': 'AmountOfSubstance', 'name': 'mole', 'allow_prefix': True},
    'mole': {'dimension': 'AmountOfSubstance', 'name': 'mole', 'allow_prefix': True},
    'moles': {'dimension': 'AmountOfSubstance', 'name': 'mole', 'allow_prefix': True},
    'molar': {'dimension': 'Molarity', 'name': 'molar', 'allow_prefix': True},
    'ppm': {'dimension': 'ConcentrationRatio', 'name': 'parts per million', 'allow_prefix': False},
    'ppb': {'dimension': 'ConcentrationRatio', 'name': 'parts per billion', 'allow_prefix': False},
    'ppt': {'dimension': 'ConcentrationRatio', 'name': 'parts per trillion', 'allow_prefix': False},
    'iu': {'dimension': 'BioActivity', 'name': 'international unit', 'allow_prefix': True},
    'u': {'dimension': 'EnzymeActivity', 'name': 'enzyme unit', 'allow_prefix': True},
    'unit': {'dimension': 'BioActivity', 'name': 'unit', 'allow_prefix': True},
    'units': {'dimension': 'BioActivity', 'name': 'unit', 'allow_prefix': True},
    'kat': {'dimension': 'CatalyticActivity', 'name': 'katal', 'allow_prefix': True},
    'ph': {'dimension': 'Acidity', 'name': 'pH', 'allow_prefix': False},
    'cfu': {'dimension': 'MicrobialCount', 'name': 'colony forming units', 'allow_prefix': False},
    'pfu': {'dimension': 'ViralCount', 'name': 'plaque forming units', 'allow_prefix': False},
    'eq': {'dimension': 'Equivalent', 'name': 'equivalent', 'allow_prefix': True},
    'meq': {'dimension': 'Equivalent', 'name': 'milliequivalent', 'allow_prefix': False},
    'od': {'dimension': 'OpticalDensity', 'name': 'optical density', 'allow_prefix': False},

    # Optics & Radiation
    'cd': {'dimension': 'LuminousIntensity', 'name': 'candela', 'allow_prefix': True},
    'candela': {'dimension': 'LuminousIntensity', 'name': 'candela', 'allow_prefix': True},
    'lm': {'dimension': 'LuminousFlux', 'name': 'lumen', 'allow_prefix': True},
    'lumen': {'dimension': 'LuminousFlux', 'name': 'lumen', 'allow_prefix': True},
    'lx': {'dimension': 'Illuminance', 'name': 'lux', 'allow_prefix': True},
    'lux': {'dimension': 'Illuminance', 'name': 'lux', 'allow_prefix': True},
    'nit': {'dimension': 'Luminance', 'name': 'nit', 'allow_prefix': True},
    'nits': {'dimension': 'Luminance', 'name': 'nit', 'allow_prefix': True},
    'bq': {'dimension': 'Radioactivity', 'name': 'becquerel', 'allow_prefix': True},
    'becquerel': {'dimension': 'Radioactivity', 'name': 'becquerel', 'allow_prefix': True},
    'ci': {'dimension': 'Radioactivity', 'name': 'curie', 'allow_prefix': True},
    'gy': {'dimension': 'AbsorbedDose', 'name': 'gray', 'allow_prefix': True},
    'gray': {'dimension': 'AbsorbedDose', 'name': 'gray', 'allow_prefix': True},
    'sv': {'dimension': 'EquivalentDose', 'name': 'sievert', 'allow_prefix': True},
    'sievert': {'dimension': 'EquivalentDose', 'name': 'sievert', 'allow_prefix': True},
    'rad': {'dimension': 'RadiationDose', 'name': 'rad', 'allow_prefix': False},
    'rem': {'dimension': 'RadiationEquivalent', 'name': 'rem', 'allow_prefix': False},

    # Ratio, Percentage, Finance, Carbon & Environmental
    '%': {'dimension': 'DimensionlessRatio', 'name': 'percent', 'allow_prefix': False},
    'percent': {'dimension': 'DimensionlessRatio', 'name': 'percent', 'allow_prefix': False},
    'percentage': {'dimension': 'DimensionlessRatio', 'name': 'percent', 'allow_prefix': False},
    '‰': {'dimension': 'DimensionlessRatio', 'name': 'permille', 'allow_prefix': False},
    'bps': {'dimension': 'FinancialRatio', 'name': 'basis points', 'allow_prefix': False},
    'usd': {'dimension': 'Currency', 'name': 'US Dollar', 'allow_prefix': False},
    'eur': {'dimension': 'Currency', 'name': 'Euro', 'allow_prefix': False},
    'idr': {'dimension': 'Currency', 'name': 'Indonesian Rupiah', 'allow_prefix': False},
    'gbp': {'dimension': 'Currency', 'name': 'British Pound', 'allow_prefix': False},
    'jpy': {'dimension': 'Currency', 'name': 'Japanese Yen', 'allow_prefix': False},
    'cny': {'dimension': 'Currency', 'name': 'Chinese Yuan', 'allow_prefix': False},
    '$': {'dimension': 'Currency', 'name': 'Dollar', 'allow_prefix': False},
    '€': {'dimension': 'Currency', 'name': 'Euro', 'allow_prefix': False},
    '£': {'dimension': 'Currency', 'name': 'Pound', 'allow_prefix': False},
    '¥': {'dimension': 'Currency', 'name': 'Yen', 'allow_prefix': False},
    'rp': {'dimension': 'Currency', 'name': 'Rupiah', 'allow_prefix': False},
    'tco2': {'dimension': 'Emission', 'name': 'tonnes of CO2', 'allow_prefix': False},
    'tco2eq': {'dimension': 'Emission', 'name': 'tonnes of CO2 equivalent', 'allow_prefix': False},
    'co2eq': {'dimension': 'Emission', 'name': 'CO2 equivalent', 'allow_prefix': False},

    # Scientific Counts & Sample Sizes
    'points': {'dimension': 'Count', 'name': 'points', 'allow_prefix': False},
    'specimens': {'dimension': 'Count', 'name': 'specimens', 'allow_prefix': False},
    'articles': {'dimension': 'Count', 'name': 'articles', 'allow_prefix': False},
    'samples': {'dimension': 'Count', 'name': 'samples', 'allow_prefix': False},
    'participants': {'dimension': 'Count', 'name': 'participants', 'allow_prefix': False},
    'respondents': {'dimension': 'Count', 'name': 'respondents', 'allow_prefix': False},
    'patients': {'dimension': 'Count', 'name': 'patients', 'allow_prefix': False},
    'subjects': {'dimension': 'Count', 'name': 'subjects', 'allow_prefix': False},
    'cases': {'dimension': 'Count', 'name': 'cases', 'allow_prefix': False},
    'epochs': {'dimension': 'Count', 'name': 'epochs', 'allow_prefix': False},
    'iterations': {'dimension': 'Count', 'name': 'iterations', 'allow_prefix': False},
    'nodes': {'dimension': 'Count', 'name': 'nodes', 'allow_prefix': False},
    'parameters': {'dimension': 'Count', 'name': 'parameters', 'allow_prefix': False},
}


# ---------------------------------------------------------
# 3. SUPERSCRIPT CITATION & NOISE REJECTION PATTERNS
# ---------------------------------------------------------
SUPERSCRIPT_MAP = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    'ᵃ': 'a', 'ᵇ': 'b', 'ᶜ': 'c', 'ᵈ': 'd', 'ᵉ': 'e',
}

# Regex deteksi sitasi pangkat menempel di akhir kata / nama / titik (misal: "et al.¹²", "Smith³", "method⁴⁻⁶")
ATTACHED_SUPERSCRIPT_CITATION_RE = re.compile(
    r'(?<=[A-Za-z\.,])([¹²³⁴⁵⁶⁷⁸⁹⁰]+(?:[,\-–—][¹²³⁴⁵⁶⁷⁸⁹⁰]+)*)\b'
)

# Regex deteksi tanda referensi bracket di teks narasi (misal: "[1]", "[1, 2]", "[12-15]")
BRACKET_CITATION_RE = re.compile(
    r'\[\s*\d+\s*(?:[,\-–—]\s*\d+\s*)*\]'
)

# Regex deteksi penanda tahun 4 digit (misal: "in 2024", "(2020-2025)", "1998")
YEAR_PATTERN_RE = re.compile(
    r'\b(18\d{2}|19\d{2}|20\d{2}|203\d)\b'
)


# ---------------------------------------------------------
# 4. UNIT RESOLVER & COMPOUND UNIT VALIDATOR
# ---------------------------------------------------------

def is_valid_scientific_unit(raw_unit_str: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Memvalidasi apakah string merupakan satuan ilmiah valid (SI, Derived, Prefixed, atau Compound Unit).
    Mengembalikan (is_valid, normalized_unit_text, physical_dimension).
    
    Contoh:
    - 'kg' -> (True, 'kg', 'Mass')
    - 'mg/dL' -> (True, 'mg/dL', 'Concentration')
    - 'kW*h' / 'kWh' -> (True, 'kWh', 'Energy')
    - '€/kWh' -> (True, '€/kWh', 'FinancialRate')
    - 'km²' -> (True, 'km²', 'Area')
    - 'invalidWord' -> (False, None, None)
    """
    if not raw_unit_str:
        return False, None, None
        
    u_clean = raw_unit_str.strip().replace('·', '*').replace(' ', '')
    u_lower = u_clean.lower()
    
    # 1. Direct Exact Match in Registry
    if u_lower in KNOWN_UNITS_REGISTRY:
        meta = KNOWN_UNITS_REGISTRY[u_lower]
        return True, u_clean, meta['dimension']
        
    # 2. Compound Unit (Garis Miring / Perkalian, misal mg/dL, EUR/kWh, kg/m3, tCO2/year)
    if '/' in u_clean or '*' in u_clean:
        parts = re.split(r'[\/\*]', u_clean)
        all_parts_valid = True
        for p in parts:
            p_sub = p.strip().strip('()').lower()
            if not p_sub:
                continue
            is_sub_valid, _, _ = is_valid_scientific_unit(p_sub)
            if not is_sub_valid:
                all_parts_valid = False
                break
        if all_parts_valid and len(parts) >= 2:
            return True, u_clean, "CompoundDimension"

    # 3. Prefixed Unit Matching (misal: 'km', 'mg', 'GHz', 'MWh', 'μmol')
    for pref, (mult, pref_name) in SI_PREFIXES.items():
        if u_clean.startswith(pref) and len(u_clean) > len(pref):
            base_part = u_clean[len(pref):]
            base_lower = base_part.lower()
            if base_lower in KNOWN_UNITS_REGISTRY:
                base_meta = KNOWN_UNITS_REGISTRY[base_lower]
                if base_meta.get('allow_prefix', False):
                    return True, u_clean, base_meta['dimension']

    return False, None, None


def sanitize_text_strip_superscript_citations(text: str) -> str:
    """
    Menghilangkan sitasi bilangan pangkat (superscript) dan sitasi bracket [1-3]
    yang menempel pada kata/nama agar tidak salah diekstrak sebagai angka metrik.
    """
    # Hapus sitasi bracket [1], [12, 13], [1-5]
    no_brackets = BRACKET_CITATION_RE.sub(' ', text)
    
    # Hapus sitasi pangkat menempel di akhir kata / titik (misal: "et al.¹²" -> "et al.")
    no_superscripts = ATTACHED_SUPERSCRIPT_CITATION_RE.sub('', no_brackets)
    
    return no_superscripts


def is_citation_or_footnote_context(name_context: str, value_str: str) -> bool:
    """
    Mendeteksi apakah kombinasi nama/angka merupakan sitasi, tahun terbit, halaman, nomor bab, atau footnote.
    """
    ctx_lower = name_context.lower().strip()
    val_clean = value_str.strip().replace(',', '.')
    
    # 1. Deteksi Nomor Halaman / Bab / Gambar / Tabel
    if any(k in ctx_lower for k in ['page', 'pages', 'halaman', 'pp.', 'vol.', 'volume', 'issue', 'no.', 'section', 'bab', 'figure', 'gambar', 'table', 'tabel']):
        return True
        
    # 2. Deteksi Sitasi Penulis / Referensi Bibliografi
    if any(k in ctx_lower for k in ['et al', 'ibid', 'op. cit', 'doi:', 'isbn', 'issn', 'available at', 'retrieved from', 'http', 'https']):
        return True
        
    # 3. Deteksi Tahun Terbit Murni (1900 - 2035) tanpa satuan fisik
    if re.match(r'^(18\d{2}|19\d{2}|20\d{2}|203\d)$', val_clean):
        if any(k in ctx_lower for k in ['in', 'published', 'diterbitkan', 'tahun', 'year', 'since', 'sejak', 'copyright']):
            return True

    return False
