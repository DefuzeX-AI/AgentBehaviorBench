#pragma once

#include "CoreMinimal.h"
#include "GameFramework/DefaultPawn.h"
#include "CameraActorBase.generated.h"

class USpringArmComponent;
class UCameraComponent;



UCLASS(Abstract)
class UE5PROJECT_API ACameraActorBase : public ADefaultPawn
{
	GENERATED_BODY()

public:
	ACameraActorBase();

	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;


	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Camera")
	double Speed = 2000.0;

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	USpringArmComponent* SpringArm;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly)
	UCameraComponent* Camera;


	virtual void OnScrollUp() {}
	virtual void OnScrollDown() {}

private:
	void OnMouseX(float Val);
	void OnMouseY(float Val);
	void OnMouseDown();
	void OnMouseUp();

	bool bClick = false;
};
