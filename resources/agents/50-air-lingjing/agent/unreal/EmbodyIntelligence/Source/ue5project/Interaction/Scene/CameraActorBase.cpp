#include "CameraActorBase.h"

#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "Components/PrimitiveComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputCoreTypes.h"
#include "Components/SphereComponent.h"

ACameraActorBase::ACameraActorBase()
{
	SpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("SpringArm"));
	SpringArm->SetupAttachment(RootComponent);

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SpringArm, USpringArmComponent::SocketName);


	if (UPrimitiveComponent* Collision = GetCollisionComponent())
	{
		Collision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}
}

void ACameraActorBase::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{

	PlayerInputComponent->BindAxisKey(EKeys::MouseX, this, &ACameraActorBase::OnMouseX);
	PlayerInputComponent->BindAxisKey(EKeys::MouseY, this, &ACameraActorBase::OnMouseY);
	PlayerInputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &ACameraActorBase::OnMouseDown);
	PlayerInputComponent->BindKey(EKeys::LeftMouseButton, IE_Released, this, &ACameraActorBase::OnMouseUp);
	PlayerInputComponent->BindKey(EKeys::MouseScrollUp, IE_Pressed, this, &ACameraActorBase::OnScrollUp);
	PlayerInputComponent->BindKey(EKeys::MouseScrollDown, IE_Pressed, this, &ACameraActorBase::OnScrollDown);
}

void ACameraActorBase::OnMouseX(float Val)
{
	if (bClick)
	{
		AddControllerYawInput(Val);
	}
}

void ACameraActorBase::OnMouseY(float Val)
{
	if (bClick)
	{
		AddControllerPitchInput(Val * -1.0f);
	}
}

void ACameraActorBase::OnMouseDown()
{
	bClick = true;
}

void ACameraActorBase::OnMouseUp()
{
	bClick = false;
}
