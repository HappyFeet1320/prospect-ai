"""
Référentiel des codes NACE belges les plus courants.
Source : SPF Économie — Nomenclature NACE-BEL 2008
"""

# Dictionnaire code NACE -> libellé français
NACE_CODES: dict[str, str] = {
    # --- A : Agriculture, sylviculture et pêche ---
    "0111": "Culture de céréales (sauf riz), de légumineuses et de graines oléagineuses",
    "0141": "Élevage de bovins et de buffles",

    # --- C : Industrie manufacturière ---
    "1011": "Transformation et conservation de la viande de boucherie",
    "1071": "Fabrication de pain et de pâtisserie fraîche",
    "1411": "Fabrication de vêtements en cuir",
    "1610": "Sciage et rabotage du bois",
    "2011": "Fabrication de gaz industriels",
    "2030": "Fabrication de peintures, vernis, encres et mastics",
    "2110": "Fabrication de produits pharmaceutiques de base",
    "2211": "Fabrication et rechapage de pneumatiques",
    "2410": "Sidérurgie",
    "2511": "Fabrication de constructions métalliques et leurs parties",
    "2512": "Fabrication de portes et fenêtres en métal",
    "2521": "Fabrication de radiateurs et de chaudières pour le chauffage central",
    "2530": "Fabrication de générateurs de vapeur",
    "2540": "Fabrication d'armes et de munitions",
    "2550": "Forge, emboutissage, estampage ; métallurgie des poudres",
    "2561": "Traitement et revêtement des métaux",
    "2562": "Décolletage, visserie",
    "2571": "Fabrication de coutellerie",
    "2572": "Fabrication de serrures et de ferrures",
    "2573": "Fabrication d'outillage",
    "2591": "Fabrication de fûts et emballages métalliques similaires",
    "2592": "Fabrication d'emballages métalliques légers",
    "2593": "Fabrication d'articles en fils métalliques, de chaînes et de ressorts",
    "2594": "Fabrication de vis et de boulons",
    "2599": "Fabrication d'autres articles métalliques",
    "2610": "Fabrication de composants électroniques",
    "2620": "Fabrication d'ordinateurs et d'équipements périphériques",
    "2630": "Fabrication d'équipements de communication",
    "2640": "Fabrication de produits électroniques grand public",
    "2670": "Fabrication de matériels optique et photographique",
    "2711": "Fabrication de moteurs, génératrices et transformateurs électriques",
    "2731": "Fabrication de câbles de fibres optiques",
    "2811": "Fabrication de moteurs et turbines",
    "2815": "Fabrication de paliers, d'engrenages et d'organes mécaniques de transmission",
    "2822": "Fabrication de matériels de levage et de manutention",
    "2825": "Fabrication d'équipements aérauliques et frigorifiques industriels",
    "2829": "Fabrication d'autres machines d'usage général",
    "2910": "Industrie automobile",
    "3011": "Construction de navires et de structures flottantes",
    "3030": "Construction aéronautique et spatiale",
    "3110": "Fabrication de meubles",
    "3290": "Autres industries manufacturières",

    # --- E : Production et distribution d'eau ---
    "3600": "Captage, traitement et distribution d'eau",
    "3811": "Collecte des déchets non dangereux",
    "3821": "Traitement et élimination des déchets non dangereux",
    "3900": "Dépollution et autres services de gestion des déchets",

    # --- F : Construction ---
    "4110": "Promotion immobilière",
    "4120": "Construction de bâtiments résidentiels et non résidentiels",
    "4211": "Construction de routes et autoroutes",
    "4221": "Construction de réseaux pour fluides",
    "4222": "Construction de réseaux électriques et de télécommunications",
    "4291": "Construction d'ouvrages hydrauliques",
    "4311": "Travaux de démolition",
    "4312": "Travaux de préparation des sites",
    "4321": "Installation électrique",
    "4322": "Travaux de plomberie et installation de chauffage et de conditionnement d'air",
    "4329": "Autres travaux d'installation",
    "4331": "Travaux de plâtrerie",
    "4332": "Travaux de menuiserie",
    "4333": "Travaux de revêtement des sols et des murs",
    "4334": "Travaux de peinture et vitrerie",
    "4339": "Autres travaux de finition",
    "4391": "Travaux de couverture",
    "4399": "Autres travaux de construction spécialisés",

    # --- G : Commerce ---
    "4511": "Commerce de voitures et de véhicules automobiles légers",
    "4520": "Entretien et réparation de véhicules automobiles",
    "4531": "Commerce de gros d'équipements automobiles",
    "4611": "Agents spécialisés dans le commerce en gros",
    "4619": "Agents du commerce en gros en produits divers",
    "4621": "Commerce de gros de céréales, tabac brut, semences et aliments pour le bétail",
    "4631": "Commerce de gros de fruits et légumes",
    "4632": "Commerce de gros de viandes et de produits à base de viande",
    "4651": "Commerce de gros d'ordinateurs, d'équipements informatiques périphériques et de logiciels",
    "4652": "Commerce de gros de composants et d'équipements électroniques et de télécommunication",
    "4661": "Commerce de gros de matériel agricole",
    "4669": "Commerce de gros d'autres machines et équipements",
    "4711": "Commerce de détail en magasin non spécialisé à prédominance alimentaire",
    "4719": "Autres commerces de détail en magasin non spécialisé",
    "4741": "Commerce de détail d'ordinateurs, d'unités périphériques et de logiciels",
    "4791": "Vente à distance",

    # --- H : Transports et entreposage ---
    "4910": "Transport ferroviaire interurbain de voyageurs",
    "4941": "Transports routiers de fret",
    "4942": "Services de déménagement",
    "5010": "Transports maritimes et côtiers de passagers",
    "5020": "Transports maritimes et côtiers de fret",
    "5110": "Transports aériens de passagers",
    "5210": "Entreposage et stockage",
    "5221": "Services auxiliaires des transports terrestres",
    "5229": "Autres services auxiliaires des transports",
    "5310": "Activités de poste dans le cadre d'une obligation de service universel",
    "5320": "Autres activités de poste et de courrier",

    # --- I : Hébergement et restauration ---
    "5510": "Hôtels et hébergement similaire",
    "5520": "Hébergement touristique et autre hébergement de courte durée",
    "5610": "Restaurants et services de restauration mobile",
    "5621": "Services des traiteurs",
    "5629": "Autres services de restauration",
    "5630": "Débits de boissons",

    # --- J : Information et communication ---
    "5811": "Édition de livres",
    "5813": "Édition de journaux",
    "5814": "Édition de revues et périodiques",
    "5819": "Autres activités d'édition",
    "5821": "Édition de jeux électroniques",
    "5829": "Édition d'autres logiciels",
    "5911": "Production de films cinématographiques, de vidéo et de programmes de télévision",
    "5912": "Post-production de films cinématographiques, de vidéo et de programmes de télévision",
    "5920": "Enregistrement sonore et édition musicale",
    "6010": "Édition et diffusion de programmes radio",
    "6020": "Programmation de télévision et diffusion de programmes",
    "6110": "Télécommunications filaires",
    "6120": "Télécommunications sans fil",
    "6130": "Télécommunications par satellite",
    "6190": "Autres activités de télécommunication",
    "6201": "Programmation informatique",
    "6202": "Conseil informatique",
    "6203": "Gestion d'installations informatiques",
    "6209": "Autres activités informatiques",
    "6311": "Traitement de données, hébergement et activités connexes",
    "6312": "Portails Internet",
    "6391": "Activités des agences de presse",
    "6399": "Autres services d'information",

    # --- K : Activités financières et d'assurance ---
    "6411": "Activités de banque centrale",
    "6419": "Autres intermédiations monétaires",
    "6420": "Activités des sociétés holding",
    "6491": "Crédit-bail",
    "6492": "Autre distribution de crédit",
    "6511": "Assurance vie",
    "6512": "Autres assurances",
    "6622": "Activités des agents et courtiers d'assurances",
    "6630": "Gestion de fonds",

    # --- L : Activités immobilières ---
    "6810": "Activités des marchands de biens immobiliers",
    "6820": "Location et exploitation de biens immobiliers propres ou loués",
    "6831": "Agences immobilières",
    "6832": "Administration de biens immobiliers",

    # --- M : Activités spécialisées, scientifiques et techniques ---
    "6910": "Activités juridiques",
    "6920": "Activités comptables",
    "7010": "Activités des sièges sociaux",
    "7021": "Conseil en relations publiques et en communication",
    "7022": "Conseil pour les affaires et autres conseils de gestion",
    "7111": "Activités d'architecture",
    "7112": "Activités d'ingénierie",
    "7120": "Activités de contrôle et analyses techniques",
    "7211": "Recherche-développement en biotechnologie",
    "7219": "Recherche-développement en autres sciences physiques et naturelles",
    "7220": "Recherche-développement en sciences humaines et sociales",
    "7311": "Activités des agences de publicité",
    "7312": "Régie publicitaire de médias",
    "7320": "Études de marché et sondages",
    "7410": "Activités spécialisées de design",
    "7420": "Activités photographiques",
    "7430": "Traduction et interprétation",
    "7490": "Autres activités spécialisées, scientifiques et techniques",
    "7500": "Activités vétérinaires",

    # --- N : Activités de services administratifs et de soutien ---
    "7710": "Location et location-bail de véhicules automobiles et de véhicules automobiles légers",
    "7720": "Location et location-bail d'articles personnels et domestiques",
    "7730": "Location et location-bail d'autres machines, équipements et biens",
    "7810": "Activités des agences de placement de main-d'œuvre",
    "7820": "Activités des agences de travail temporaire",
    "7830": "Autre mise à disposition de ressources humaines",
    "7911": "Activités des agences de voyage",
    "7912": "Activités des voyagistes",
    "8010": "Activités de sécurité privée",
    "8020": "Activités liées aux systèmes de sécurité",
    "8110": "Activités combinées de soutien lié aux bâtiments",
    "8121": "Nettoyage courant des bâtiments",
    "8122": "Autres activités de nettoyage des bâtiments et nettoyage industriel",
    "8130": "Services d'aménagement paysager",
    "8211": "Services administratifs combinés de bureau",
    "8219": "Photocopie, préparation de documents et autres activités spécialisées de soutien de bureau",
    "8220": "Activités de centres d'appels",
    "8230": "Organisation de foires, salons professionnels et congrès",
    "8291": "Activités des agences de recouvrement de factures et des sociétés d'information financière sur la clientèle",
    "8299": "Autres activités de soutien aux entreprises",

    # --- O : Administration publique et défense ---
    "8411": "Administration générale (publique)",
    "8412": "Administration des activités économiques",
    "8413": "Administration des activités de santé, de formation, de culture et des autres services sociaux",
    "8421": "Affaires étrangères",
    "8422": "Défense",
    "8423": "Justice",
    "8424": "Activités d'ordre public et de sécurité",
    "8425": "Services du feu et de secours",
    "8430": "Sécurité sociale obligatoire",

    # --- P : Enseignement ---
    "8510": "Enseignement pré-primaire",
    "8520": "Enseignement primaire",
    "8531": "Enseignement secondaire général",
    "8532": "Enseignement secondaire technique ou professionnel",
    "8541": "Enseignement post-secondaire non supérieur",
    "8542": "Enseignement supérieur",
    "8551": "Enseignements de disciplines sportives et d'activités de loisirs",
    "8552": "Enseignements culturels",
    "8553": "Enseignement de la conduite",
    "8559": "Autres enseignements",
    "8560": "Activités de soutien à l'enseignement",

    # --- Q : Santé humaine et action sociale ---
    "8610": "Activités hospitalières",
    "8621": "Activité des médecins généralistes",
    "8622": "Activité des médecins spécialistes",
    "8623": "Pratique dentaire",
    "8690": "Autres activités pour la santé humaine",
    "8710": "Hébergement médicalisé",
    "8720": "Hébergement social pour personnes handicapées mentales, malades mentales et toxicomanes",
    "8730": "Hébergement social pour personnes âgées ou handicapées physiques",
    "8790": "Autres formes d'hébergement social",
    "8810": "Action sociale sans hébergement pour personnes âgées et pour personnes handicapées",
    "8891": "Accueil de jeunes enfants",
    "8899": "Autre action sociale sans hébergement",

    # --- R : Arts, spectacles et activités récréatives ---
    "9001": "Arts du spectacle vivant",
    "9002": "Activités de soutien au spectacle vivant",
    "9003": "Création artistique",
    "9004": "Gestion de salles de spectacle et activités connexes",
    "9101": "Activités des bibliothèques et des archives",
    "9102": "Activités des musées",
    "9200": "Organisation de jeux de hasard et d'argent",
    "9311": "Gestion d'installations sportives",
    "9312": "Activités de clubs de sports",
    "9319": "Autres activités liées au sport",
    "9329": "Autres activités récréatives et de loisirs",

    # --- S : Autres activités de services ---
    "9411": "Activités des organisations patronales et consulaires",
    "9412": "Activités des organisations professionnelles",
    "9420": "Activités des syndicats de salariés",
    "9491": "Activités des organisations religieuses",
    "9499": "Activités des autres organisations associatives",
    "9511": "Réparation d'ordinateurs et d'équipements périphériques",
    "9512": "Réparation d'équipements de communication",
    "9521": "Réparation de produits électroniques grand public",
    "9522": "Réparation d'appareils électroménagers et d'équipements pour la maison et le jardin",
    "9601": "Blanchisserie-teinturerie",
    "9602": "Coiffure et soins de beauté",
    "9609": "Autres services personnels",
}


def search_nace(query: str, limit: int = 10) -> list[dict]:
    """Recherche de codes NACE par mot-clé (libellé)."""
    query_lower = query.lower()
    results = []
    for code, label in NACE_CODES.items():
        if query_lower in label.lower():
            results.append({"code": code, "label": label})
    return results[:limit]


def get_nace_label(code: str) -> str:
    """Retourne le libellé d'un code NACE, ou le code lui-même si inconnu."""
    return NACE_CODES.get(code, f"Code NACE {code}")


def get_nace_division(code: str) -> str:
    """Retourne la division (2 premiers chiffres) d'un code NACE."""
    return code[:2] if len(code) >= 2 else code


def are_codes_related(code1: str, code2: str) -> bool:
    """Vérifie si deux codes NACE sont dans la même division (2 chiffres)."""
    return get_nace_division(code1) == get_nace_division(code2)
