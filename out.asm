extern printf
section .text
	global main
main:
	push ebp
	mov ebp, esp
	sub esp, 4
	mov dword [ebp-4], 1
	push dword [ebp-4]
	push __t_0
	call printf
	mov dword [__t_1], eax
	add esp, 8
	mov eax, 1
	mov esp, ebp
	pop ebp
	ret
section	.data
	__t_1	dd	0
	getInt:	db	"%d"	
	__t_0:	db	"%d", 0