# Intégration Home Assistant - ES Énergies (Strasbourg)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)

Intégration personnalisée Home Assistant pour récupérer automatiquement les données de consommation d'électricité (Linky) et de gaz d'**Électricité de Strasbourg (ES Énergies - SuiviConso)**.

## Fonctionnalités

- **Configuration via l'interface graphique (Config Flow)** : Aucun fichier YAML requis !
- **Prise en charge du 2FA dans l'interface** : Le code à 6 chiffres reçu par email est demandé directement dans une pop-up Home Assistant lors de la première installation.
- **Zéro redemande de 2FA ensuite** : Sauvegarde de l'empreinte d'appareil de confiance (`device_id`) pour un renouvellement de session 100% transparent.
- **Compatible Tableau de Bord Énergie (Energy Dashboard)** : L'entité `Index de consommation` possède les classes `total_increasing` et `device_class: energy`.
- **Plus de 18 capteurs créés automatiquement** (format `sensor.linky_<pdl>_<nom_capteur>`) :
  - `sensor.linky_<pdl>_index_de_consommation` (Index officiel en kWh)
  - `sensor.linky_<pdl>_consommation_d_hier` (Conso de la veille en kWh)
  - `sensor.linky_<pdl>_cout_d_hier` (Coût de la veille en € TTC)
  - `sensor.linky_<pdl>_consommation_du_mois` (Conso mensuelle en kWh)
  - `sensor.linky_<pdl>_cout_du_mois` (Coût mensuel en € TTC)
  - `sensor.linky_<pdl>_estimation_fin_de_mois` (Projection kWh fin de mois)
  - `sensor.linky_<pdl>_facture_estimee_fin_de_mois` (Projection facture € fin de mois)
  - `sensor.linky_<pdl>_puissance_maximale` (Pmax atteinte en W)
  - `sensor.linky_<pdl>_courbe_de_charge` (Consommation de la veille au pas de 30 min)
  - `sensor.linky_<pdl>_qualite_de_telereleve` (Qualité télérelève Linky en %)
  - Et bien d'autres (température, DJU, empreinte carbone, talon veille, etc.)

---

## Installation

### Méthode 1 : Via HACS (Recommandé)

1. Ouvrez **HACS** dans votre Home Assistant.
2. Cliquez sur les 3 petits points en haut à droite -> **Dépôts personnalisés**.
3. Ajoutez l'URL de votre dépôt GitHub et choisissez la catégorie **Intégration**.
4. Cliquez sur **Télécharger**.
5. Redémarrez Home Assistant.

### Méthode 2 : Installation Manuelle

1. Copiez le dossier `custom_components/es_energies` dans le dossier `/config/custom_components/` de votre serveur Home Assistant.
2. Redémarrez Home Assistant.

---

## Configuration

1. Dans Home Assistant, allez dans **Paramètres** -> **Appareils et services** -> **Ajouter une intégration**.
2. Recherchez **ES Énergies (Strasbourg - SuiviConso)**.
3. Saisissez votre adresse email et votre mot de passe d'espace client.
4. Si demandé, entrez le code de sécurité reçu par email.
5. Vos capteurs et votre appareil Linky sont créés instantanément !

---

## Intégration dans le tableau de bord Énergie (Energy Dashboard)

1. Allez dans **Paramètres** -> **Tableaux de bord** -> **Énergie**.
2. Dans la section **Réseau électrique** -> **Ajouter une consommation**.
3. Sélectionnez le capteur `sensor.compteur_linky_index_compteur_linky`.
