-- Apache AGE graph for ContextMap KG (name must match configs/contextmap.yaml kg.age.graph_name)
LOAD 'age';
SET search_path = ag_catalog, public;
SELECT create_graph('contextmap');
