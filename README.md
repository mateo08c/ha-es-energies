<p align="center">
  <img src="icon.png" width="128" height="128" alt="Logo ÉS Énergies x Home Assistant" />
</p>

<h1 align="center">ES Énergies - Intégration Home Assistant</h1>

<p align="center">
  <a href="https://github.com/hacs/default"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS" /></a>
  <a href="https://github.com/mateo08c/ha-es-energies/releases"><img src="https://img.shields.io/github/v/release/mateo08c/ha-es-energies?style=flat-square" alt="GitHub release" /></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" /></a>
</p>

Intégration Home Assistant permettant de récupérer automatiquement les index, consommations, coûts et courbes de charge de vos compteurs d'électricité (**Linky**) et de **Gaz**, directement depuis l'Espace Client d'**Électricité de Strasbourg (ÉS)**.

## Prérequis

- Avoir un contrat actif auprès d'**Électricité de Strasbourg (ÉS)**.
- Un accès fonctionnel à l'Espace Client sur [espaceclient.es.fr](https://espaceclient.es.fr/).
- Un compteur communicant **Linky** (et/ou Gaz) raccordé.


## Données remontées

### Électricité (Compteur Linky)

> **Note** : Les identifiants d'entités sont générés automatiquement au format `sensor.linky_<pdl>_<nom_capteur>` où `<pdl>` correspond à votre numéro de Point de Livraison (ex. `01234567891011`).

| Nom de l'entité | Identifiant HA (`entity_id`) | Unité | Description |
| :--- | :--- | :---: | :--- |
| **Index de consommation** | `sensor.linky_<pdl>_index_de_consommation` | `kWh` | Index officiel de facturation (compatible tableau de bord Énergie) |
| **Index heures creuses** | `sensor.linky_<pdl>_index_heures_creuses` | `kWh` | Index séparé Heures Creuses (créé si option double tarif) |
| **Index heures pleines** | `sensor.linky_<pdl>_index_heures_pleines` | `kWh` | Index séparé Heures Pleines (créé si option double tarif) |
| **Consommation d'hier** | `sensor.linky_<pdl>_consommation_d_hier` | `kWh` | Volume d'électricité consommé la veille |
| **Coût d'hier** | `sensor.linky_<pdl>_cout_d_hier` | `€` | Dépense estimée de la veille (TTC) |
| **Consommation du mois** | `sensor.linky_<pdl>_consommation_du_mois` | `kWh` | Cumul consommé depuis le début du mois |
| **Coût du mois** | `sensor.linky_<pdl>_cout_du_mois` | `€` | Dépense cumulée du mois en cours (TTC) |
| **Estimation fin de mois** | `sensor.linky_<pdl>_estimation_fin_de_mois` | `kWh` | Projection du volume total consommé à la fin du mois |
| **Facture estimée fin de mois** | `sensor.linky_<pdl>_facture_estimee_fin_de_mois` | `€` | Montant estimé de la prochaine facture |
| **Puissance maximale** | `sensor.linky_<pdl>_puissance_maximale` | `W` | Pic de puissance atteint (Pmax) pour surveiller le risque de disjonction |
| **Courbe de charge** | `sensor.linky_<pdl>_courbe_de_charge` | `kWh` | Consommation de la veille au pas de 30 minutes (48 points en attributs) |
| **Consommation bruit de fond (Veille)** | `sensor.linky_<pdl>_consommation_bruit_de_fond_veille` | `kWh` | Talon de consommation continue (avec coût et part de la facture en attributs) |
| **Empreinte carbone du mois** | `sensor.linky_<pdl>_empreinte_carbone_du_mois` | `kg` | Émissions de CO₂ avec détail du mix énergétique officiel ÉS (nucléaire/renouvelable) |
| **Température extérieure moyenne** | `sensor.linky_<pdl>_temperature_exterieure_moyenne` | `°C` | Température moyenne relevée sur votre commune |
| **Degrés jours unifiés (DJU)** | `sensor.linky_<pdl>_degres_jours_unifies_dju` | - | Indicateur climatique pour analyser vos besoins en chauffage |

### Gaz naturel *(uniquement si contrat gaz actif)*

> **Note** : Les identifiants d'entités gaz suivent le format `sensor.compteur_gaz_<pdl>_<nom_capteur>`.

| Nom de l'entité | Identifiant HA (`entity_id`) | Unité | Description |
| :--- | :--- | :---: | :--- |
| **Index de consommation** | `sensor.compteur_gaz_<pdl>_index_de_consommation` | `m³` | Index du compteur gaz pour le tableau de bord Énergie |
| **Consommation d'hier** | `sensor.compteur_gaz_<pdl>_consommation_d_hier` | `kWh` | Volume de gaz consommé la veille |
| **Coût d'hier** | `sensor.compteur_gaz_<pdl>_cout_d_hier` | `€` | Coût estimé du gaz consommé la veille |
| **Consommation du mois** | `sensor.compteur_gaz_<pdl>_consommation_du_mois` | `kWh` | Volume cumulé du mois en cours |
| **Dernière synchronisation** | `sensor.compteur_gaz_<pdl>_derniere_synchronisation` | - | Horodatage du dernier rafraîchissement des données gaz |

### Informations de contrat & Diagnostic

| Nom de l'entité | Identifiant HA (`entity_id`) | Unité / Type | Description |
| :--- | :--- | :---: | :--- |
| **Titulaire du compte** | `sensor.linky_<pdl>_titulaire_du_compte` | Diagnostic (Texte) | Nom & prénom du titulaire, métadonnées du compte en attributs |
| **Point de livraison** | `sensor.linky_<pdl>_point_de_livraison` | Diagnostic (Numérique) | Numéro de PDL officiel (14 chiffres) |
| **Adresse de raccordement** | `sensor.linky_<pdl>_adresse_de_raccordement` | Diagnostic (Texte) | Adresse postale du point de livraison |
| **Puissance souscrite** | `sensor.linky_<pdl>_puissance_souscrite` | `kVA` | Puissance souscrite (option tarifaire Base/HC en attributs) |
| **Qualité de télérelève** | `sensor.linky_<pdl>_qualite_de_telereleve` | `%` | Pourcentage de complétude des relevés de la veille |
| **Dernière synchronisation** | `sensor.linky_<pdl>_derniere_synchronisation` | Diagnostic (Timestamp) | Date et heure de la dernière synchronisation réussie avec ÉS |

## Installation

### Via HACS (Recommandé)

1. Ouvrez **HACS** > **Intégrations**.
2. Cliquez sur les trois points en haut à droite > **Dépôts personnalisés**.
3. Renseignez l'URL :
   ```text
   https://github.com/mateo08c/ha-es-energies
   ```
4. Sélectionnez la catégorie **Intégration** puis cliquez sur **Ajouter**.
5. Téléchargez la dernière version et **redémarrez Home Assistant**.

## Configuration

1. Allez dans **Paramètres** > **Appareils et services** > **Ajouter une intégration**.
2. Recherchez **ES Énergies (Strasbourg - SuiviConso)**.
3. Saisissez votre email et votre mot de passe d'Espace Client ÉS.
4. Entrez le code à 6 chiffres envoyé sur votre boîte email par le serveur d'authentification d'ÉS.
5. C'est tout. L'appareil `Linky` et tous ses capteurs sont créés.

> **Note sur le code 2FA** : Grâce à la mémorisation de l'appareil (cookies de session Keycloak sécurisés), ce code à 6 chiffres ne vous est demandé qu'une seule fois à l'installation. Les rafraîchissements futurs se font de manière transparente en arrière-plan.

## Configuration du tableau de bord Énergie

Pour intégrer votre Linky au tableau de bord natif Home Assistant :

1. Ouvrez **Paramètres** > **Tableaux de bord** > **Énergie**.
2. Dans **Réseau électrique** > **Consommation du réseau**, cliquez sur **Ajouter une consommation**.
3. Choisissez le capteur :
   - `Index de consommation` (`sensor.linky_XXXXXX_index_de_consommation`)

## Exemples de cartes Lovelace

### Carte résumé standard (Mushroom ou Tile)

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-title-card
    title: Électricité de Strasbourg
    subtitle: Suivi Linky

  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: sensor.linky_XXXXXX_consommation_d_hier
        name: Conso hier
        icon: mdi:flash

      - type: custom:mushroom-entity-card
        entity: sensor.linky_XXXXXX_cout_d_hier
        name: Coût hier
        icon: mdi:currency-eur

  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: sensor.linky_XXXXXX_consommation_du_mois
        name: Conso mois
        icon: mdi:calendar-month

      - type: custom:mushroom-entity-card
        entity: sensor.linky_XXXXXX_facture_estimee_fin_de_mois
        name: Facture estimée
        icon: mdi:cash-multiple

  - type: custom:mushroom-entity-card
    entity: sensor.linky_XXXXXX_puissance_maximale
    name: Puissance max atteinte
    icon: mdi:gauge
```

### Graphique de la courbe de charge (ApexCharts)

Si vous utilisez [ApexCharts Card](https://github.com/RomRider/apexcharts-card), vous pouvez tracer le profil de consommation de la veille toutes les 30 minutes :

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Courbe de charge Linky (Hier)
  show_states: true
  colorize_states: true
series:
  - entity: sensor.linky_XXXXXX_courbe_de_charge
    name: Puissance moyenne (30 min)
    type: column
    data_generator: |
      return entity.attributes.points_30min.map((p) => {
        return [new Date(p.start).getTime(), p.kwh * 2000]; // Conversion kWh/30min en Watts
      });
```

## Mentions légales & Avertissements

- **Projet non officiel** : Ce projet est un développement communautaire et bénévole, indépendant d'Électricité de Strasbourg (ÉS), ÉS Énergies, EDF et Enedis.
- **Marques déposées** : Les dénominations et logos « ÉS », « Électricité de Strasbourg », « SuiviConso » et « Linky » sont des marques déposées appartenant à leurs propriétaires respectifs. Ils sont utilisés ici exclusivement à des fins d'identification logicielle et de compatibilité technique (*usage loyal nominatif*).
- **Données et vie privée** : Les échanges s'effectuent directement entre votre instance Home Assistant et les serveurs sécurisés d'Électricité de Strasbourg. Aucun serveur intermédiaire n'est utilisé. Vos identifiants restent stockés localement sur votre machine.

## Licence

Distribué sous licence libre **MIT**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.
