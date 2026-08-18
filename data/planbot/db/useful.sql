select * from products where product_type = 'bond';

select * from holdings;

select qualitative_profile from planbot.clients where client_id = 'PB-HK-000001-8';

update planbot.clients set qualitative_profile = 'Experienced executive with strong income stream. Actively manages portfolio; prefers evidence-based decisions. Open to structured products and tactical equity plays. Love investing in Technology sector and open to high concentration portfolio. Two children approaching university age — education funding is a near-term priority.' where 
 client_id = 'PB-HK-000001-8';

update planbot.clients set qualitative_profile = 'Experienced executive with strong income stream. Actively manages portfolio; prefers evidence-based decisions. Open to structured products and tactical equity plays. Has expressed concern about inflation eroding idle cash. Two children approaching university age — education funding is a near-term priority.' where client_id = 'PB-HK-000001-8';

