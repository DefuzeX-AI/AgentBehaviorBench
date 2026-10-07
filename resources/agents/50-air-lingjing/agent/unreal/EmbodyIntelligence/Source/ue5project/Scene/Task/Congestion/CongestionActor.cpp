#include "CongestionActor.h"
#include "UObject/ConstructorHelpers.h"
#include "Materials/MaterialInstanceDynamic.h"

ACongestionActor::ACongestionActor()
{
	// Static mesh asset references
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CarBMW(TEXT("/Game/ArtRes/Base_Art/Car/mesh/Car_BMW.Car_BMW"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Car5(TEXT("/Game/ArtRes/Base_Art/Car/mesh/Car_5.Car_5"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CarCityBus(TEXT("/Game/ArtRes/Base_Art/Car/mesh/Car_City_Bus.Car_City_Bus"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CarCityBus1(TEXT("/Game/ArtRes/Base_Art/Car/mesh/Car_City_Bus1.Car_City_Bus1"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CarDoubleDeckerBus(TEXT("/Game/ArtRes/Base_Art/Car/mesh/Car_Double_Decker_bus.Car_Double_Decker_bus"));

	// CarMesh1 - Car_BMW at (870, -3560, 350) Yaw=90
	CarMesh1 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh1"));
	CarMesh1->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh1->SetStaticMesh(CarBMW.Object); }
	CarMesh1->SetRelativeLocation(FVector(870.0f, -3560.0f, 350.0f));
	CarMesh1->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh2 - Car_BMW at (890, -600, 350) Yaw=90
	CarMesh2 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh2"));
	CarMesh2->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh2->SetStaticMesh(CarBMW.Object); }
	CarMesh2->SetRelativeLocation(FVector(890.0f, -600.0f, 350.0f));
	CarMesh2->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh3 - Car_City_Bus at (390, -1610, 350) Yaw=90
	CarMesh3 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh3"));
	CarMesh3->SetupAttachment(SceneComponent);
	if (CarCityBus.Succeeded()) { CarMesh3->SetStaticMesh(CarCityBus.Object); }
	CarMesh3->SetRelativeLocation(FVector(390.0f, -1610.0f, 350.0f));
	CarMesh3->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh4 - Car_City_Bus1 at (880, -1680, 350) Yaw=90
	CarMesh4 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh4"));
	CarMesh4->SetupAttachment(SceneComponent);
	if (CarCityBus1.Succeeded()) { CarMesh4->SetStaticMesh(CarCityBus1.Object); }
	CarMesh4->SetRelativeLocation(FVector(880.0f, -1680.0f, 350.0f));
	CarMesh4->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh5 - Car_Double_Decker_bus at (360, 0, 350) Yaw=90
	CarMesh5 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh5"));
	CarMesh5->SetupAttachment(SceneComponent);
	if (CarDoubleDeckerBus.Succeeded()) { CarMesh5->SetStaticMesh(CarDoubleDeckerBus.Object); }
	CarMesh5->SetRelativeLocation(FVector(360.0f, 0.0f, 350.0f));
	CarMesh5->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh6 - Car_5 at (-320, 0, 350) Yaw=90
	CarMesh6 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh6"));
	CarMesh6->SetupAttachment(SceneComponent);
	if (Car5.Succeeded()) { CarMesh6->SetStaticMesh(Car5.Object); }
	CarMesh6->SetRelativeLocation(FVector(-320.0f, 0.0f, 350.0f));
	CarMesh6->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh7 - Car_5 at (-860, 20, 350) Yaw=90
	CarMesh7 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh7"));
	CarMesh7->SetupAttachment(SceneComponent);
	if (Car5.Succeeded()) { CarMesh7->SetStaticMesh(Car5.Object); }
	CarMesh7->SetRelativeLocation(FVector(-860.0f, 20.0f, 350.0f));
	CarMesh7->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh8 - Car_BMW at (-310, -710, 350) Yaw=90
	CarMesh8 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh8"));
	CarMesh8->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh8->SetStaticMesh(CarBMW.Object); }
	CarMesh8->SetRelativeLocation(FVector(-310.0f, -710.0f, 350.0f));
	CarMesh8->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh9 - Car_BMW at (-340, -1430, 350) Yaw=90
	CarMesh9 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh9"));
	CarMesh9->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh9->SetStaticMesh(CarBMW.Object); }
	CarMesh9->SetRelativeLocation(FVector(-340.0f, -1430.0f, 350.0f));
	CarMesh9->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh10 - Car_City_Bus1 at (-780, -1440, 350) Yaw=90
	CarMesh10 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh10"));
	CarMesh10->SetupAttachment(SceneComponent);
	if (CarCityBus1.Succeeded()) { CarMesh10->SetStaticMesh(CarCityBus1.Object); }
	CarMesh10->SetRelativeLocation(FVector(-780.0f, -1440.0f, 350.0f));
	CarMesh10->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh11 - Car_BMW at (900, -2840, 350) Yaw=90
	CarMesh11 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh11"));
	CarMesh11->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh11->SetStaticMesh(CarBMW.Object); }
	CarMesh11->SetRelativeLocation(FVector(900.0f, -2840.0f, 350.0f));
	CarMesh11->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh12 - Car_5 at (900, 0, 350) Yaw=90
	CarMesh12 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh12"));
	CarMesh12->SetupAttachment(SceneComponent);
	if (Car5.Succeeded()) { CarMesh12->SetStaticMesh(Car5.Object); }
	CarMesh12->SetRelativeLocation(FVector(900.0f, 0.0f, 350.0f));
	CarMesh12->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh13 - Car_City_Bus1 at (370, -3360, 350) Yaw=90
	CarMesh13 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh13"));
	CarMesh13->SetupAttachment(SceneComponent);
	if (CarCityBus1.Succeeded()) { CarMesh13->SetStaticMesh(CarCityBus1.Object); }
	CarMesh13->SetRelativeLocation(FVector(370.0f, -3360.0f, 350.0f));
	CarMesh13->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh14 - Car_5 at (350, -2110, 350) Yaw=90
	CarMesh14 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh14"));
	CarMesh14->SetupAttachment(SceneComponent);
	if (Car5.Succeeded()) { CarMesh14->SetStaticMesh(Car5.Object); }
	CarMesh14->SetRelativeLocation(FVector(350.0f, -2110.0f, 350.0f));
	CarMesh14->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh15 - Car_Double_Decker_bus at (-250, -2690, 350) Yaw=90
	CarMesh15 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh15"));
	CarMesh15->SetupAttachment(SceneComponent);
	if (CarDoubleDeckerBus.Succeeded()) { CarMesh15->SetStaticMesh(CarDoubleDeckerBus.Object); }
	CarMesh15->SetRelativeLocation(FVector(-250.0f, -2690.0f, 350.0f));
	CarMesh15->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh16 - Car_City_Bus at (-220, -4300, 350) Yaw=90
	CarMesh16 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh16"));
	CarMesh16->SetupAttachment(SceneComponent);
	if (CarCityBus.Succeeded()) { CarMesh16->SetStaticMesh(CarCityBus.Object); }
	CarMesh16->SetRelativeLocation(FVector(-220.0f, -4300.0f, 350.0f));
	CarMesh16->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh17 - Car_5 at (-810, -2560, 350) Yaw=90
	CarMesh17 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh17"));
	CarMesh17->SetupAttachment(SceneComponent);
	if (Car5.Succeeded()) { CarMesh17->SetStaticMesh(Car5.Object); }
	CarMesh17->SetRelativeLocation(FVector(-810.0f, -2560.0f, 350.0f));
	CarMesh17->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh18 - Car_BMW at (-820, -3160, 350) Yaw=90
	CarMesh18 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh18"));
	CarMesh18->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh18->SetStaticMesh(CarBMW.Object); }
	CarMesh18->SetRelativeLocation(FVector(-820.0f, -3160.0f, 350.0f));
	CarMesh18->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh19 - Car_5 at (-840, -3800, 350) Yaw=90
	CarMesh19 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh19"));
	CarMesh19->SetupAttachment(SceneComponent);
	if (Car5.Succeeded()) { CarMesh19->SetStaticMesh(Car5.Object); }
	CarMesh19->SetRelativeLocation(FVector(-840.0f, -3800.0f, 350.0f));
	CarMesh19->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));

	// CarMesh20 - Car_BMW at (-850, -4400, 350) Yaw=90
	CarMesh20 = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CarMesh20"));
	CarMesh20->SetupAttachment(SceneComponent);
	if (CarBMW.Succeeded()) { CarMesh20->SetStaticMesh(CarBMW.Object); }
	CarMesh20->SetRelativeLocation(FVector(-850.0f, -4400.0f, 350.0f));
	CarMesh20->SetRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));
}

void ACongestionActor::InitTaskPoint(const FTaskPointInfo& InTaskPointInfo)
{
	Super::InitTaskPoint(InTaskPointInfo);

	InitTagWidget(FSColor(255, 229, 0, 0.5f), TaskPointInfo.TaskPointId);
}

void ACongestionActor::BeginPlay()
{
	Super::BeginPlay();
}
